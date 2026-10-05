"""Server fallback for NAS uploads. If the NAS is down, the file is kept in
uploads/nas-outbox/ and queued in pending_nas_uploads. nas_outbox_flush.py
(systemd timer, every 2 min) pushes it later and removes the server copy.
While queued, nas.download_app_file serves the server copy."""
import os
import uuid
from datetime import datetime
from flask import current_app

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import PendingNasUpload


def _outbox_dir():
    return os.path.join(current_app.config['UPLOAD_FOLDER'], 'nas-outbox')


def _local_path(row):
    return os.path.join(_outbox_dir(), row.local_name)


def _remove_local(row):
    try:
        os.remove(_local_path(row))
    except OSError:
        pass


def _queue(file_bytes, nas_path, error):
    """Write the bytes to the outbox and queue them. Re-queuing the same
    nas_path replaces the older bytes."""
    os.makedirs(_outbox_dir(), exist_ok=True)
    row = PendingNasUpload.query.filter_by(nas_path=nas_path).first()
    if row is None:
        row = PendingNasUpload(nas_path=nas_path, local_name=f'{uuid.uuid4().hex}.bin')
        db.session.add(row)
    with open(_local_path(row), 'wb') as f:
        f.write(file_bytes)
    row.attempts = 0
    row.last_error = error[:1000]
    row.updated_at = datetime.utcnow()
    db.session.commit()


def upload_or_queue(file_bytes, nas_folder_path, filename):
    """Upload to the NAS, trying once. If the NAS is down, keep the file on the
    server and queue it. Returns True if uploaded now, False if queued.
    Raises OSError only if the server copy can't be written either."""
    from app.modules.core.shared.services import nas
    nas_path = f'{nas_folder_path}/{filename}'
    try:
        nas.upload_app_file(file_bytes, nas_folder_path, filename, _max_attempts=1)
    except RuntimeError as e:
        current_app.logger.warning(f'NAS down, queued {nas_path!r} on the server: {e}')
        _queue(file_bytes, nas_path, str(e))
        return False
    # Uploaded directly, so an older queued copy must not overwrite it later.
    discard(nas_path)
    return True


def pending_bytes(nas_path):
    """The server copy of a queued file, or None if nothing is queued."""
    row = PendingNasUpload.query.filter_by(nas_path=nas_path).first()
    if row is None:
        return None
    try:
        with open(_local_path(row), 'rb') as f:
            return f.read()
    except OSError as e:
        current_app.logger.error(f'Queued file missing on server for {nas_path!r}: {e}')
        return None


def discard(nas_path):
    """Drop a queued file (server copy and row). Returns True if one was queued."""
    row = PendingNasUpload.query.filter_by(nas_path=nas_path).first()
    if row is None:
        return False
    _remove_local(row)
    db.session.delete(row)
    db.session.commit()
    return True


def flush():
    """Push every queued file to the NAS, oldest first. Returns (sent, left).
    Checks the NAS once up front, so a down NAS costs one timeout, not one per file."""
    from app.modules.core.shared.services import nas

    rows = PendingNasUpload.query.order_by(PendingNasUpload.created_at).all()
    if not rows:
        return 0, 0
    if not nas.is_reachable():
        return 0, len(rows)

    sent = 0
    for row in rows:
        row_id, stamp, nas_path = row.id, row.updated_at, row.nas_path
        try:
            with open(_local_path(row), 'rb') as f:
                data = f.read()
        except OSError as e:
            current_app.logger.error(f'Outbox file missing for {nas_path!r}, dropping: {e}')
            db.session.delete(row)
            db.session.commit()
            continue

        folder, filename = nas_path.rsplit('/', 1)
        try:
            nas.upload_app_file(data, folder, filename, _max_attempts=1)
        except RuntimeError as e:
            row.attempts += 1
            row.last_error = str(e)[:1000]
            db.session.commit()
            continue

        # Re-check: the app may have deleted or replaced it during the upload.
        db.session.expire_all()
        current = db.session.get(PendingNasUpload, row_id)
        if current is None:
            nas.delete_app_file(nas_path)  # deleted in the app meanwhile, so undo
        elif current.updated_at == stamp:
            _remove_local(current)
            db.session.delete(current)
            db.session.commit()
            sent += 1
        # else: newer bytes were queued mid-upload; the next run sends them.

    return sent, PendingNasUpload.query.count()
