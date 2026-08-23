from app.modules.core.shared.extensions import db
from datetime import datetime


class ProjectStatusLog(db.Model):
    __tablename__ = 'project_status_logs'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    project = db.relationship('Project', backref=db.backref('status_logs', cascade='all, delete-orphan'))
    changed_by = db.relationship('User', foreign_keys=[changed_by_id])

    def __repr__(self):
        return f'<ProjectStatusLog project={self.project_id} status={self.status} open={self.ended_at is None}>'


class ProjectCustomerStatusLog(db.Model):
    __tablename__ = 'project_customer_status_logs'

    id = db.Column(db.Integer, primary_key=True)
    project_customer_id = db.Column(db.Integer, db.ForeignKey('project_customers.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    project_customer = db.relationship('ProjectCustomer', backref=db.backref('status_logs', cascade='all, delete-orphan'))
    changed_by = db.relationship('User', foreign_keys=[changed_by_id])

    def __repr__(self):
        return f'<ProjectCustomerStatusLog pc={self.project_customer_id} status={self.status} open={self.ended_at is None}>'


class DeliverableStatusLog(db.Model):
    __tablename__ = 'deliverable_status_logs'

    id = db.Column(db.Integer, primary_key=True)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    deliverable = db.relationship('Deliverable', backref=db.backref('status_logs', cascade='all, delete-orphan'))
    changed_by = db.relationship('User', foreign_keys=[changed_by_id])

    def __repr__(self):
        return f'<DeliverableStatusLog deliverable={self.deliverable_id} status={self.status} open={self.ended_at is None}>'

    # ProjectFile Class — stores reference files uploaded to a project by CS or admin
