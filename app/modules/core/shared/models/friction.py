from datetime import datetime

from app.modules.core.shared.extensions import db


class FrictionLogEntry(db.Model):
    """One Friction Log post (what is not working for the team), grouped by
    week. Everyone reads; can_write_friction() decides who posts."""
    __tablename__ = 'friction_log_entries'

    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    # The Monday of the week this entry belongs to; the thread groups on it.
    week_start = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship('User', foreign_keys=[author_id])

    def __repr__(self):
        return f'<FrictionLogEntry {self.id} week {self.week_start}>'
