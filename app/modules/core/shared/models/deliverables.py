from app.modules.core.shared.extensions import db
from datetime import datetime


# A deliverable type for one client + customer, with an optional reference image for briefs.
class DeliverableType(db.Model):
    __tablename__ = 'deliverable_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False) 
    reference_image = db.Column(db.String(255), nullable=True)
    template_filename = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_custom = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('Client', backref='deliverable_types')
    customer = db.relationship('Customer', backref='deliverable_types')
    disciplines = db.relationship('DeliverableTypeDiscipline', backref='deliverable_type', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<DeliverableType {self.name}>'


# A design team ('2D', '3D', 'Technical') a deliverable type needs.
class DeliverableTypeDiscipline(db.Model):
    __tablename__ = 'deliverable_type_disciplines'

    id = db.Column(db.Integer, primary_key=True)
    deliverable_type_id = db.Column(db.Integer, db.ForeignKey('deliverable_types.id'), nullable=False)
    team = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f'<DeliverableTypeDiscipline {self.team} for type {self.deliverable_type_id}>'


# One deliverable within a project.
class Deliverable(db.Model):
    __tablename__ = 'deliverables'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    project_customer_id = db.Column(db.Integer, db.ForeignKey('project_customers.id'), nullable=True)
    deliverable_type_id = db.Column(db.Integer, db.ForeignKey('deliverable_types.id'), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    reference_image = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default='in_progress', nullable=False)
    design_deadline = db.Column(db.Date, nullable=True)
    design_deadline_time = db.Column(db.Time, nullable=True)
    installation_deadline = db.Column(db.Date, nullable=True)
    teams = db.Column(db.String(100), nullable=True)  # comma-separated e.g. "3D,Technical"
    revision_comment = db.Column(db.Text, nullable=True)
    revision_count = db.Column(db.Integer, default=0, nullable=False)
    flagged_for_revision = db.Column(db.Boolean, default=False, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    needs_technical = db.Column(db.Boolean, default=False, nullable=False)
    technical_status = db.Column(db.String(50), nullable=True)
    # 2D, 3D and Technical are independent Pre-Production streams, each with a
    # needs_* flag and its own status.
    needs_2d = db.Column(db.Boolean, default=False, nullable=False)
    needs_3d = db.Column(db.Boolean, default=False, nullable=False)
    status_2d = db.Column(db.String(50), nullable=True)
    status_3d = db.Column(db.String(50), nullable=True)

    # overlaps= silences the warning: project_deliverables and project_ref map the same FK.
    project = db.relationship('Project', back_populates='project_deliverables', overlaps='project_deliverables,project_ref')
    deliverable_type = db.relationship('DeliverableType', backref='deliverables')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    disciplines = db.relationship('DeliverableAssignment', backref='deliverable', cascade='all, delete-orphan')
    brief_flags = db.relationship('BriefFlag', back_populates='deliverable', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Deliverable {self.name} status={self.status}>'


# A designer assigned to a deliverable for one team, and who assigned them.
class DeliverableAssignment(db.Model):
    __tablename__ = 'deliverable_assignments'

    id = db.Column(db.Integer, primary_key=True)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)
    designer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    team = db.Column(db.String(20), nullable=False)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    designer = db.relationship('User', foreign_keys=[designer_id], backref='deliverable_assignments')
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])

    def __repr__(self):
        return f'<DeliverableAssignment deliverable={self.deliverable_id} designer={self.designer_id}>'


class DeliverablePreproductionEvent(db.Model):
    """Append-only log of Pre-Production flags on a deliverable (a stream sent
    back for reupload; see _can_manage_preproduction). Separate from
    ProjectSubmissionEvent because a deliverable can reach Pre-Production with
    no submission. event_type is 'preprod_flag'."""
    __tablename__ = 'deliverable_preproduction_events'

    id = db.Column(db.Integer, primary_key=True)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)
    event_type = db.Column(db.String(30), nullable=False)
    stream = db.Column(db.String(20), nullable=True)  # '2d' | '3d' | 'technical'
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    deliverable = db.relationship('Deliverable',
                                  backref=db.backref('preproduction_events', cascade='all, delete-orphan',
                                                     order_by='DeliverablePreproductionEvent.created_at'))
    author = db.relationship('User', foreign_keys=[author_id])

    def __repr__(self):
        return f'<DeliverablePreproductionEvent deliverable={self.deliverable_id} type={self.event_type}>'
