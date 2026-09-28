"""
HSE entry attachments. Bytes are stored on the NAS via core/shared's
service; this module keeps the record. Uploads are synchronous so the user
knows the file was saved.
"""
from flask import abort, current_app, jsonify, request, send_file
from flask_login import login_required
from io import BytesIO

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import (
    effective_user, require, require_api,
)
from app.modules.core.shared.lib.utils import log_activity
from app.modules.core.shared.services.nas import (
    delete_app_file, download_app_file, upload_app_file,
)
from app.modules.hse.lib.files import (
    ALLOWED_EXTENSIONS, MAX_BYTES, MIME_TYPES, PREVIEWABLE, extension,
    folder_for, is_allowed, safe_segment,
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
        # The NAS service already retried; report the failure to the user.
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
    """Streams the file through the app so the NAS is never exposed and
    view_hse is enforced."""
    attachment = HseAttachment.query.get_or_404(attachment_id)
    try:
        file_bytes = download_app_file(attachment.nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'HSE attachment download failed ({attachment.nas_path}): {e}')
        abort(502)
    return send_file(BytesIO(file_bytes), as_attachment=True,
                     download_name=attachment.original_filename)


@hse_bp.route('/files/<int:attachment_id>/preview')
@login_required
@require('view_hse')
def preview_attachment(attachment_id):
    """The file served inline for preview.

    Response shape is read by core/shared/js/preview.js: the file when it
    can render, else JSON {error} with 200 so the modal shows the reason.
    """
    attachment = HseAttachment.query.get_or_404(attachment_id)
    kind = extension(attachment.original_filename)
    if kind not in PREVIEWABLE:
        return jsonify({'error': 'That file type has no preview.'}), 200

    try:
        file_bytes = download_app_file(attachment.nas_path)
    except RuntimeError as e:
        current_app.logger.error(
            f'HSE attachment preview failed ({attachment.nas_path}): {e}')
        return jsonify({'error': 'That file could not be read from storage.'}), 200

    return send_file(BytesIO(file_bytes), mimetype=MIME_TYPES[kind],
                     download_name=attachment.original_filename)


@hse_bp.route('/files/<int:attachment_id>', methods=['DELETE'])
@login_required
@require_api('manage_hse')
def delete_attachment(attachment_id):
    attachment = HseAttachment.query.get_or_404(attachment_id)
    entry = attachment.entry
    actor = effective_user()

    # Delete the row first. delete_app_file never raises, so a NAS outage
    # leaves an orphaned file, never a row the user thinks is gone.
    name = attachment.original_filename
    db.session.delete(attachment)
    db.session.commit()
    delete_app_file(attachment.nas_path)

    log_activity('hse_file_deleted', f'{actor.name} removed {name} from {entry.ref}',
                 user=actor, entity_type='hse_entry', entity_name=entry.ref, entity_id=entry.id)
    return jsonify({'deleted': attachment_id})
