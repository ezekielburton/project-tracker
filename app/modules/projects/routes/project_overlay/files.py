"""
project_overlay/files.py — Reference Files (upload/download/preview/delete/
download-all), job-number generation, and Submission file serving
(download/preview, both the submission and its individual files).
"""

from flask import request, jsonify
from flask_login import login_required, current_user

from app.modules.core.shared.models import Project
from app.modules.core.shared.lib.decorators import role_required

from ._common import project_overlay_bp

# ── Reference Files — upload / download / preview / delete ──
# Serves the Details tab's Reference Files card (_details_reference_files.html
# + project_details_card.js). Lives here because Reference Files is part of
# Details, already in this blueprint.

@project_overlay_bp.route('/projects/<int:project_id>/upload-file', methods=['POST'])
@login_required
@role_required('admin', 'cs', 'management')
def upload_project_file(project_id):
    """Handle reference file uploads for a project. CS and admin only."""
    from app.modules.core.shared.models import ProjectFile, User
    from flask import session, current_app

    project = Project.query.get_or_404(project_id)
    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    can_manage_files = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in {a.user_id for a in project.secondary_cs_assignments}
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )
    if not can_manage_files:
        return jsonify({'success': False, 'error': 'You are lacking permissions to perform this action.'}), 403

    # Check a file was actually included in the request
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    # Only allow safe file types
    allowed_extensions = {'jpg', 'jpeg', 'png', 'pdf', 'docx', 'xlsx', 'pptx', 'zip', 'dwg',
                          'mp4', 'mov', 'avi', 'webm', 'mkv', 'wmv', 'm4v'}
    original_filename = file.filename
    ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''

    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': f'File type .{ext} not allowed'}), 400

    # Read file bytes before anything else (file stream can only be read once)
    file_bytes = file.read()

    # Upload directly to NAS - synchronous, user waits for confirmation
    from app.modules.core.shared.services.nas import upload_app_file, build_file_path
    nas_file_path = build_file_path(project, 'Reference Files', original_filename)
    nas_folder = nas_file_path.rsplit('/',1)[0]
    try:
        upload_app_file(file_bytes, nas_folder, original_filename)
    except RuntimeError as e:
        current_app.logger.error(f'Reference file upload failed for project {project_id}: {e}')
        return jsonify({'success': False, 'error': 'File could not be saved to storage. Please try again.'}), 502

    # Save record - Filename column stores the NAS filename (Same as original)
    project_file = ProjectFile(
        project_id=project_id,
        filename=original_filename,
        original_filename=original_filename,
        file_type=ext,
        uploaded_by_id=actor.id
    )

    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity, file_type_label
    db.session.add(project_file)
    db.session.commit()

    log_activity('file_uploaded', f'{current_user.name} added {file_type_label(ext)} as a reference file to "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({
        'success': True,
        'file': {
            'id': project_file.id,
            'original_filename': original_filename,
            'file_type': ext,
            'uploaded_by': actor.name
        }
    })


@project_overlay_bp.route('/projects/files/<int:file_id>/download')
@login_required
def download_project_file(file_id):
    """Serve a reference file for download. All authenticated users can download. Download is served from the NAS"""
    from app.modules.core.shared.models import ProjectFile
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    import io
    from flask import send_file, current_app

    project_file = ProjectFile.query.get_or_404(file_id)
    project = Project.query.get(project_file.project_id)

    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Reference file download failed (file_id={file_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)

    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=project_file.original_filename
    )


@project_overlay_bp.route('/projects/<int:project_id>/reference-files/download-all')
@login_required
def download_all_reference_files(project_id):
    """Zips every reference file for this project and returns a download link."""
    from app.modules.core.shared.lib.zip_utils import build_zip
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from flask import url_for as _url_for

    project = Project.query.get_or_404(project_id)
    files = project.reference_files
    if not files:
        return jsonify({'success': False, 'error': 'No reference files to download.'}), 400

    zip_files = []
    seen_names = {}
    for f in files:
        nas_path = build_file_path(project, 'Reference Files', f.original_filename)
        try:
            content = download_app_file(nas_path)
        except RuntimeError:
            continue # skip a file that failed to fetch rather than failing the whole zip

        # Disambiguate if two files happen to share a filename — zipfile
        # allows duplicate entry names, but most extractors handle that badly.
        name = f.original_filename
        if name in seen_names:
            seen_names[name] += 1
            base, dot, ext = name.rpartition('.')
            name = f'{base} ({seen_names[name]}).{ext}' if dot else f'{name} ({seen_names[name]})'
        else:
            seen_names[name] = 0

        zip_files.append((name, content))

    if not zip_files:
        return jsonify({'success': False, 'error': 'Could not fetch any files from the NAS.'}), 502

    zip_id = build_zip(zip_files, f'{project.name} - Reference Files.zip')
    return jsonify({'success': True, 'download_url': _url_for('api.zip_download', zip_id=zip_id)})


@project_overlay_bp.route('/projects/files/<int:file_id>/preview')
@login_required
def preview_project_file(file_id):
    """Serve a reference file for inline preview. Only browser-renderable types
    (PDF, common images) are supported; anything else returns 'no preview'."""
    from app.modules.core.shared.models import ProjectFile
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from flask import send_file, jsonify, current_app
    import io

    # Maps a stored file extension to the mimetype the browser needs to
    # render it inline. Anything not in here just isn't previewable.
    PREVIEWABLE_TYPES = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }

    project_file = ProjectFile.query.get_or_404(file_id)

    mimetype = PREVIEWABLE_TYPES.get((project_file.file_type or '').lower())
    if not mimetype:
        # Check the type before touching the NAS — no point fetching something
        # we can't render.
        return jsonify({
            'success': False,
            'error': 'No preview available for this file type — download instead.'
        }), 415 # Unsupported Media Type

    project = Project.query.get(project_file.project_id)
    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Reference file preview failed (file_id={file_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading it instead.'
        }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=project_file.original_filename
    )


@project_overlay_bp.route('/projects/files/<int:file_id>/delete', methods=['POST'])
@login_required
def delete_project_file(file_id):
    """Delete a reference file. Admin/Management (any project), this project's CS lead/secondary CS, or this projects project owner"""
    from app.modules.core.shared.models import ProjectFile, User
    from flask import session

    project_file = ProjectFile.query.get_or_404(file_id)
    project = Project.query.get(project_file.project_id)

    emulating_id = session.get('emulating_user_id')
    actor = User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user

    can_manage_files = (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in {a.user_id for a in project.secondary_cs_assignments}
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
    )
    if not can_manage_files:
        return jsonify({'success': False, 'error': 'You are lacking permissions to perform this action.'}), 403

    # Delete from NAS
    from app.modules.core.shared.services.nas import delete_app_file, build_file_path
    nas_path = build_file_path(project, 'Reference Files', project_file.original_filename)
    delete_app_file(nas_path)

    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.lib.utils import log_activity
    log_activity('file_deleted', f'{actor.name} removed a reference file from "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    db.session.delete(project_file)
    db.session.commit()

    return jsonify({'success': True})


# ── Job number generation ──
# The one live caller is the create-mode overlay (project_overlay_create.js).
# NOTE: still uses the non-atomic MAX(job_number)+1 pattern — an atomic fix is
# separate work, not done here.

@project_overlay_bp.route('/projects/generate-job-number', methods=['GET'])
@login_required
@role_required('admin', 'cs', 'management', 'project_owner')
def generate_job_number():
    FOC_PAD = 3 # Digits: 3 -> FOC-001 ... FOC-999. Change to 4 for FOC-1000+

    #Pull all existing FOC job numbers from the DB
    existing = Project.query.with_entities(Project.job_number).filter(
        Project.job_number.like('FOC-%')
    ).all()

    # Parse the numeric suffix from each, collect into a list
    used_numbers = []
    for (jn,) in existing:
        suffix = jn[4:] # strip 'FOC- prefix
        if suffix.isdigit():
            used_numbers.append(int(suffix))

    # Next number is max +1, or 1 if none exist yet
    next_num = (max(used_numbers) + 1) if used_numbers else 1
    job_number = 'FOC-' + str(next_num).zfill(FOC_PAD)

    return jsonify({'job_number': job_number})


# ── Submission file serving — download / preview ──
# Serves the Submissions tab's preview/download buttons
# (_submissions_draft_card.html) for the active deck and history. Lives here
# alongside the other overlay file-serving routes.

@project_overlay_bp.route('/projects/submission/<int:submission_id>/download')
@login_required
def download_submission(submission_id):
    from app.modules.core.shared.models import ProjectSubmission
    from flask import send_file
    import io, os

    submission = ProjectSubmission.query.get_or_404(submission_id)
    project = Project.query.get(submission.project_id)

    # All files live on NAS — upload route never saves to local disk
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from flask import current_app
    nas_path = build_file_path(project, 'Submissions', submission.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Submission download failed (id={submission_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)
    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=submission.original_filename
    )


def _load_submission_file_bytes(sub_file, project):
    """Return a submission file's raw bytes from wherever it lives now: the
    local draft cache (storage_location == 'cache') or the NAS (default).
    Raises RuntimeError on failure, matching download_app_file's contract."""
    if sub_file.storage_location == 'cache':
        import os
        path = sub_file.local_cache_path
        if not path or not os.path.isfile(path):
            raise RuntimeError(
                f'cached submission file missing on disk '
                f'(file_id={sub_file.id}, path={path!r})'
            )
        with open(path, 'rb') as fh:
            return fh.read()

    # storage_location == 'nas'. Two shapes, told apart by the submission's
    # stored deck name:
    # 1. Overlay flow — the draft was zipped into one archive at Submit to
    #    Client (deck name ends .zip); this file is a member, extract it by
    #    original_filename.
    # 2. Old flow — a supplementary upload stored as its own NAS object.
    from app.modules.core.shared.services.nas import download_app_file, build_file_path

    submission = sub_file.submission
    deck_name = submission.original_filename if submission else None
    if deck_name and deck_name.lower().endswith('.zip'):
        import io
        import zipfile
        zip_bytes = download_app_file(build_file_path(project, 'Submissions', deck_name))
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                return zf.read(sub_file.original_filename)
        except KeyError:
            raise RuntimeError(
                f'member {sub_file.original_filename!r} not found in zip {deck_name!r} '
                f'(file_id={sub_file.id})'
            )
        except zipfile.BadZipFile as e:
            raise RuntimeError(f'corrupt submission zip {deck_name!r} (file_id={sub_file.id}): {e}')

    # Old supplementary file — read it directly.
    nas_path = build_file_path(project, 'Submissions', sub_file.original_filename)
    return download_app_file(nas_path)


@project_overlay_bp.route('/projects/submission/file/<int:file_id>/preview')
@login_required
def preview_submission_file(file_id):
    """Serve a supplementary submission file for inline preview — same
    PDF/image-only restriction as reference-file previews."""
    from app.modules.core.shared.models import ProjectSubmissionFile
    from flask import send_file, jsonify
    import io

    PREVIEWABLE_TYPES = {
        'pdf': 'application/pdf',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }

    extra = ProjectSubmissionFile.query.get_or_404(file_id)

    mimetype = PREVIEWABLE_TYPES.get((extra.file_type or '').lower())
    if not mimetype:
        return jsonify ({
            'success': False,
            'error': 'No preview available for this file type - download instead.'
            }), 415
    
    project = Project.query.get(extra.project_id)
    from flask import current_app
    try:
        file_bytes = _load_submission_file_bytes(extra, project)
    except RuntimeError as e:
        from flask import current_app
        current_app.logger.error(f'Submission file preview failed (file_id={file_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading it instead.'
        }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=extra.original_filename
    )


@project_overlay_bp.route('/projects/submission/file/<int:file_id>/download')
@login_required
def download_submission_file(file_id):
    """Download a supplementary file attached to a submission."""
    from app.modules.core.shared.models import ProjectSubmissionFile
    from flask import send_file
    import io

    extra = ProjectSubmissionFile.query.get_or_404(file_id)
    project = Project.query.get(extra.project_id)

    from flask import current_app
    try:
        file_bytes = _load_submission_file_bytes(extra, project)
    except RuntimeError as e:
        current_app.logger.error(f'Submission extra-file download failed (file_id={file_id}): {e}')
        return ('File could not be retrieved from storage. '
                'Please try again or contact support.', 502)
    return send_file(
        io.BytesIO(file_bytes),
        as_attachment=True,
        download_name=extra.original_filename
    )


@project_overlay_bp.route('/projects/submission/<int:submission_id>/preview')
@login_required
def preview_submission(submission_id):
    """Serve a submission deck for inline preview. PDFs stream as-is; PPTX
    decks are converted to PDF on the fly (browsers can't render PowerPoint)."""
    from app.modules.core.shared.models import ProjectSubmission
    from app.modules.core.shared.services.nas import download_app_file, build_file_path
    from app.modules.projects.lib.pptx_convert import convert_pptx_to_pdf
    from flask import send_file, jsonify, current_app
    import io, subprocess

    submission = ProjectSubmission.query.get_or_404(submission_id)
    project = Project.query.get(submission.project_id)

    nas_path = build_file_path(project, 'Submissions', submission.original_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Submission preview NAS fetch failed (id={submission_id}): {e}')
        return jsonify({
            'success': False,
            'error': 'File could not be retrieved from storage. Try downloading instead.'
        }), 502

    if submission.file_type.lower() == 'pptx':
        try:
            file_bytes = convert_pptx_to_pdf(file_bytes)
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            current_app.logger.warning(
                f'Preview conversion failed for submission {submission_id}: {e}'
            )
            return jsonify({
                'success': False,
                'error': 'Preview unavailable for this file — try downloading instead.'
            }), 502

    return send_file(
        io.BytesIO(file_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=submission.original_filename.rsplit('.', 1)[0] + '.pdf'
    )
