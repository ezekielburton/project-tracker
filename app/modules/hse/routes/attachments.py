"""
HSE — files filed against an entry.

Bytes go to the NAS through core/shared's service; this module owns the
record of where they went. Uploads are synchronous so the officer knows
whether his evidence actually landed.
"""
from flask import abort, current_app, jsonify, request, send_file
from flask_login import login_required
from io import BytesIO

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import effective_user, require_api
from app.modules.core.shared.lib.utils import log_activity
from app.modules.core.shared.services.nas import (
    delete_app_file, download_app_file, upload_app_file,
)
from app.modules.hse.lib.files import (
    ALLOWED_EXTENSIONS, MAX_BYTES, extension, folder_for, is_allowed, safe_segment,
)
from app.modules.hse.models import HseAttachment, HseEntry
from app.modules.hse.routes.blueprint import hse_bp


def _serialize(attachment):
    return {
        'id': attachment.id,
        'name': attachment.original_filename,
        'type': attachment.file_type,
        'uploaded_by': attachment.uploaded_by.name if attachment.uploaded_by else None,
    }


@hse_bp.route('/entry/<int:entry_id>/files', methods=['POST'])
@login_required
@require_api('manage_hse')
def upload_attachment(entry_id):
    entry = HseEntry.query.get_or_404(entry_id)
    actor = effective_user()

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    upload = request.files['file']
    if not upload.filename:
        return jsonify({'error': 'No file selected'}), 400
    if not is_allowed(upload.filename):
        allowed = ', '.join(sorted(ALLOWED_EXTENSIONS))
        return jsonify({'error': f'That file type is not allowed. Accepted: {allowed}'}), 400

    file_bytes = upload.read()
    if len(file_bytes) > MAX_BYTES:
        return jsonify({'error': 'That file is over 25 MB.'}), 400

    folder = folder_for(entry)
    stored_name = safe_segment(upload.filename)
    try:
        upload_app_file(file_bytes, folder, stored_name)
    except RuntimeError as e:
        # The NAS service already retried and logged; the officer needs to
        # know his evidence is not filed rather than assume it is.
        current_app.logger.error(f'HSE attachment upload failed for {entry.ref}: {e}')
        return jsonify({'error': 'The file could not be saved to storage. Please try again.'}), 502

    attachment = HseAttachment(
        entry_id=entry.id,
        filename=stored_name,
        original_filename=upload.filename,
        file_type=extension(upload.filename),
        nas_path=f'{folder}/{stored_name}',
        uploaded_by_id=actor.id,
    )
    db.session.add(attachment)
    db.session.commit()

    log_activity('hse_file_uploaded', f'{actor.name} attached {upload.filename} to {entry.ref}',
                 user=actor, entity_type='hse_entry', entity_name=entry.ref, entity_id=entry.id)
    return jsonify({'file': _serialize(attachment)}), 201


@hse_bp.route('/files/<int:attachment_id>')
@login_required
@require_api('view_hse')
def download_attachment(attachment_id):
    """Streamed through the app rather than linked directly, so the NAS is
    never exposed and view_hse is actually enforced."""
    attachment = HseAttachment.query.get_or_404(attachment_id)
    try:
        file_bytes = download_app_file(attachment.nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'HSE attachment download failed ({attachment.nas_path}): {e}')
        abort(502)
    return send_file(BytesIO(file_bytes), as_attachment=True,
                     download_name=attachment.original_filename)


@hse_bp.route('/files/<int:attachment_id>', methods=['DELETE'])
@login_required
@require_api('manage_hse')
def delete_attachment(attachment_id):
    attachment = HseAttachment.query.get_or_404(attachment_id)
    entry = attachment.entry
    actor = effective_user()

    # The record goes first. delete_app_file never raises, so a NAS that is
    # briefly unreachable leaves an orphaned file rather than a row pointing
    # at something the officer thinks he deleted.
    name = attachment.original_filename
    db.session.delete(attachment)
    db.session.commit()
    delete_app_file(attachment.nas_path)

    log_activity('hse_file_deleted', f'{actor.name} removed {name} from {entry.ref}',
                 user=actor, entity_type='hse_entry', entity_name=entry.ref, entity_id=entry.id)
    return jsonify({'deleted': attachment_id})
