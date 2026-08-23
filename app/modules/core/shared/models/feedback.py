from app.modules.core.shared.extensions import db
from datetime import datetime


class FeatureRequest(db.Model):
    __tablename__ = 'feature_requests'

    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    description     = db.Column(db.Text, nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status          = db.Column(db.String(50), nullable=False, default='requested')
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    submitter = db.relationship('User', backref='feature_requests')
    upvotes   = db.relationship('FeatureRequestUpvote', backref='feature',
                                cascade='all, delete-orphan')
    comments  = db.relationship('FeatureRequestComment',
                                foreign_keys='FeatureRequestComment.feature_id',
                                backref='feature', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<FeatureRequest {self.title}>'


class FeatureRequestUpvote(db.Model):
    __tablename__ = 'feature_request_upvotes'

    id         = db.Column(db.Integer, primary_key=True)
    feature_id = db.Column(db.Integer, db.ForeignKey('feature_requests.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('feature_id', 'user_id'),)

    voter = db.relationship('User', backref='feature_upvotes')

    def __repr__(self):
        return f'<FeatureRequestUpvote feature={self.feature_id} user={self.user_id}>'


class FeatureRequestComment(db.Model):
    __tablename__ = 'feature_request_comments'

    id         = db.Column(db.Integer, primary_key=True)
    feature_id = db.Column(db.Integer, db.ForeignKey('feature_requests.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    parent_id  = db.Column(db.Integer, db.ForeignKey('feature_request_comments.id'), nullable=True)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author  = db.relationship('User', backref='feature_comments')
    replies = db.relationship(
        'FeatureRequestComment',
        foreign_keys='FeatureRequestComment.parent_id',
        backref=db.backref('fr_parent', remote_side='FeatureRequestComment.id'),
        lazy='select'
    )

    def __repr__(self):
        return f'<FeatureRequestComment {self.id} on feature {self.feature_id}>'


class BugReport(db.Model):
    __tablename__ = 'bug_reports'

    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    description     = db.Column(db.Text, nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status          = db.Column(db.String(50), default='in_queue')
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    submitter = db.relationship('User', backref='bug_reports')
    comments  = db.relationship('BugReportComment',
                                foreign_keys='BugReportComment.bug_id',
                                cascade='all, delete-orphan')

    def __repr__(self):
        return f'<BugReport {self.id}: {self.title}>'


class BugReportComment(db.Model):
    __tablename__ = 'bug_report_comments'

    id         = db.Column(db.Integer, primary_key=True)
    bug_id     = db.Column(db.Integer, db.ForeignKey('bug_reports.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    parent_id  = db.Column(db.Integer, db.ForeignKey('bug_report_comments.id'), nullable=True)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author  = db.relationship('User', foreign_keys=[user_id], backref='bug_comments')
    replies = db.relationship(
        'BugReportComment',
        foreign_keys='BugReportComment.parent_id',
        backref=db.backref('br_parent', remote_side='BugReportComment.id'),
        lazy='select'
    )

    def __repr__(self):
        return f'<BugReportComment {self.id} on bug {self.bug_id}>'
    
#  ---- Wiki -------------------------------
