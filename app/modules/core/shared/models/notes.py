from app.modules.core.shared.extensions import db
from datetime import datetime


class ProjectNote(db.Model):
    """A project chat message (human-written; ActivityLog is machine-written)."""
    __tablename__ = 'project_notes'

    id = db.Column(db.Integer, primary_key=True)
    # Indexed: every Projects page load runs MAX(created_at) GROUP BY project_id
    # here (_bulk_activity_and_chat_at), and Postgres does not index FKs itself.
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    file_link = db.Column(db.String(500), nullable=True)
    tags = db.Column(db.JSON, nullable=True)  # {'mentions': [user_id, ...]}
    # SET NULL: deleting the quoted message keeps the reply.
    reply_to_id = db.Column(db.Integer, db.ForeignKey('project_notes.id', ondelete='SET NULL'), nullable=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    # attachment_filename is the stored name on the NAS; the original name is for display only.
    attachment_filename = db.Column(db.String(255), nullable=True)
    attachment_original_filename = db.Column(db.String(255), nullable=True)
    attachment_type = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref=db.backref('notes', cascade='all, delete-orphan'))
    author = db.relationship('User', foreign_keys=[author_id])
    reply_to = db.relationship('ProjectNote', remote_side=[id], foreign_keys=[reply_to_id])

    def display_text(self):
        """The message body, or a Photo/Video placeholder for a caption-less attachment."""
        if self.body:
            return self.body
        if self.attachment_type == 'image':
            return '📷 Photo'
        if self.attachment_type == 'video':
            return '🎥 Video'
        return ''

    def __repr__(self):
        return f'<ProjectNote project={self.project_id} author={self.author_id}>'


class ProjectNoteReaction(db.Model):
    """One person's emoji reaction to a chat message; at most one per person
    per message."""
    __tablename__ = 'project_note_reactions'
    __table_args__ = (
        db.UniqueConstraint('note_id', 'user_id', name='uq_project_note_reactions_note_user'),
    )

    id = db.Column(db.Integer, primary_key=True)
    note_id = db.Column(db.Integer, db.ForeignKey('project_notes.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    emoji = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    note = db.relationship('ProjectNote', backref=db.backref('reactions', cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<ProjectNoteReaction note={self.note_id} user={self.user_id} emoji={self.emoji!r}>'
