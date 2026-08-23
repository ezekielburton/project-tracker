from app.modules.core.shared.extensions import db
from datetime import datetime


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_name = db.Column(db.String(200), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    changes = db.Column(db.JSON, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])


class SidebarClick(db.Model):
    """Analytics table — records every sidebar link click.
    Used by admin to see which tools and pages are most used.
    Written to by POST /sidebar/track (fire-and-forget from sidebar.js)."""
    __tablename__ = 'sidebar_clicks'

    id         = db.Column(db.Integer, primary_key=True)
    link_name  = db.Column(db.String(100), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user_role  = db.Column(db.String(50), nullable=True)
    clicked_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def __repr__(self):
        return f'<SidebarClick {self.link_name} by user {self.user_id}>'
