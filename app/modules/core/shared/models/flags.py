from app.modules.core.shared.extensions import db
from datetime import datetime


class BriefFlag(db.Model):
    __tablename__ = 'brief_flags'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=True)
    flag_type = db.Column(db.String(20), nullable=False)  # 'project', 'deliverable', 'concept', 'kv'
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_resolved = db.Column(db.Boolean, default=False, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    project = db.relationship('Project', back_populates='brief_flags')
    deliverable = db.relationship('Deliverable', back_populates='brief_flags')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])
    messages = db.relationship('BriefFlagMessage', backref='flag', cascade='all, delete-orphan', order_by='BriefFlagMessage.created_at')

    def __repr__(self):
        return f'<BriefFlag project={self.project_id} type={self.flag_type} resolved={self.is_resolved}>'


class DecisionFlag(db.Model):
    __tablename__ = 'decision_flags'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow )
    note = db.Column(db.Text, nullable=False)
    is_resolved = db.Column(db.Boolean, default=False, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolution_note = db.Column(db.Text, nullable=True)

    project = db.relationship('Project', back_populates='decision_flags')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])
    messages = db.relationship('DecisionFlagMessage', backref='flag', cascade='all, delete-orphan', order_by='DecisionFlagMessage.created_at')

    def __repr__(self):
        return f'<DecisionFlag project={self.project_id} resolved={self.is_resolved}>'


class DecisionFlagMessage(db.Model):
    __tablename__ = 'decision_flag_messages'

    id = db.Column(db.Integer, primary_key=True)
    flag_id = db.Column(db.Integer, db.ForeignKey('decision_flags.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship('User', foreign_keys=[author_id])

    def __repr__(self):
        return f'<DecisionFlagMessage flag={self.flag_id} author={self.author_id}>'


class BriefFlagMessage(db.Model):
    __tablename__ = 'brief_flag_messages'

    id = db.Column(db.Integer, primary_key=True)
    flag_id = db.Column(db.Integer, db.ForeignKey('brief_flags.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship('User', foreign_keys=[author_id])

    def __repr__(self):
        return f'<BriefFlagMessage flag={self.flag_id} author={self.author_id}>'
