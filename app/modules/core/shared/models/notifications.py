from app.modules.core.shared.extensions import db
from datetime import datetime


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    triggered_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    link = db.Column(db.String(500), nullable=True)

    # Relationships
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='notifications')
    project = db.relationship('Project', backref='notifications')
    triggered_by = db.relationship('User', foreign_keys=[triggered_by_id])

    def __repr__(self):
        return f'<Notification {self.id} for user {self.recipient_id}>'


class NotificationSound (db.Model):
    """
    An admin-uploaded audio file users can choose to play when a new notification arrives.
    Files themselves alive on the disk at app/static/sounds/
    This table only tracks metadata + which file backs each entry.
    """

    __tablename__ = 'notification_sounds'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # Display label
    filename = db.Column(db.String(255), nullable=False) # Actual file on disk
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def __repr__(self):
        return f'<NotificationSound {self.name}>'
