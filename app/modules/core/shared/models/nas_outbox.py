from app.modules.core.shared.extensions import db
from datetime import datetime


class PendingNasUpload(db.Model):
    """A file kept on the server while the NAS was down. nas_outbox_flush.py
    pushes it to nas_path, then deletes the row and the server copy."""
    __tablename__ = 'pending_nas_uploads'

    id         = db.Column(db.Integer, primary_key=True)
    # Full NAS destination, e.g. /Projects/2026/P&G/Summer/Reference Files/brief.pdf
    nas_path   = db.Column(db.String(1000), unique=True, nullable=False)
    # File name inside uploads/nas-outbox/ (not a full path, so it survives a server move)
    local_name = db.Column(db.String(64), nullable=False)
    attempts   = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # Set only when new bytes are queued, so the flush can tell if it was replaced mid-upload
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<PendingNasUpload {self.nas_path} attempts={self.attempts}>'
