from datetime import datetime

from app.modules.core.shared.extensions import db


class ChatTrayProject(db.Model):
    """One person's Chat tray state for one project: added by hand, pinned, or
    hidden until someone posts again. Projects with activity need no row."""
    __tablename__ = 'chat_tray_projects'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'project_id', name='uq_chat_tray_projects_user_project'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    # Keeps a project listed even with no messages.
    added_at = db.Column(db.DateTime, nullable=True)
    # Holds the row above every unpinned one, whatever the activity.
    pinned_at = db.Column(db.DateTime, nullable=True)
    # Drops the row until a message newer than this arrives.
    hidden_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    project = db.relationship('Project', foreign_keys=[project_id])

    def __repr__(self):
        return f'<ChatTrayProject user={self.user_id} project={self.project_id}>'
