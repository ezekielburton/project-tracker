from app.modules.core.shared.extensions import db
from datetime import datetime


# DeliverableType Class. Handles relationships for deliverable types, which are linked to clients and customers. Also stores reference images for deliverable types, which can be used in the project brief to help designers understand the requirements.
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


# Child class, links deliverable types to disciplines/teams. This allows us to specify which teams are needed for each deliverable type, which can then be used in the project brief to help designers understand the requirements and ensure the right teams are assigned to each project.  
class DeliverableTypeDiscipline(db.Model):
    __tablename__ = 'deliverable_type_disciplines'

    id = db.Column(db.Integer, primary_key=True)
    deliverable_type_id = db.Column(db.Integer, db.ForeignKey('deliverable_types.id'), nullable=False)
    team = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f'<DeliverableTypeDiscipline {self.team} for type {self.deliverable_type_id}>'


# Represents an individual deliverable within a project. revision_comment
# holds the free-text feedback CS sends when requesting a revision, shown to
# the designer so they know what to change.
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
    # 2D and 3D are independent Pre-Production streams, each with its own
    # needs_* flag and status, matching how Design treats 2D/3D/Technical as
    # three separate teams.
    needs_2d = db.Column(db.Boolean, default=False, nullable=False)
    needs_3d = db.Column(db.Boolean, default=False, nullable=False)
    status_2d = db.Column(db.String(50), nullable=True)
    status_3d = db.Column(db.String(50), nullable=True)

    # overlaps= tells SQLAlchemy these relationships intentionally share the same
    # foreign key — project_deliverables and project_ref are the other side of this mapping
    project = db.relationship('Project', back_populates='project_deliverables', overlaps='project_deliverables,project_ref')
    deliverable_type = db.relationship('DeliverableType', backref='deliverables')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    disciplines = db.relationship('DeliverableAssignment', backref='deliverable', cascade='all, delete-orphan')
    brief_flags = db.relationship('BriefFlag', back_populates='deliverable', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Deliverable {self.name} status={self.status}>'


# DeliverableAssignment Class, records who is assigned to each deliverable, and who made that assignment.
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
    """Append-only history log for one deliverable's Pre-Production review
    cycle (admin/management/CS Lead/Project Owner flagging a technical/
    artwork release upload for reupload — see _can_manage_preproduction).

    Its own table — deliberately NOT ProjectSubmissionEvent — for two
    reasons: (1) pre-production isn't submission-scoped, a deliverable can
    land here via Skip to Pre-Production with no ProjectSubmission
    involved at all, so a submission_id FK wouldn't always have anything
    to point at; (2) this history is kept separate from Submissions' own
    event log rather than filtered out of a shared one.

    event_type is 'preprod_flag' (a stream bounced back for reupload, message required) — a distinct value so
    later KPI queries ("average revision rounds") can filter cleanly
    without guessing from free text. stream distinguishes which release
    stream ('technical'/'artwork') the flag was about, for KPI breakdowns
    that need that granularity."""
    __tablename__ = 'deliverable_preproduction_events'

    id = db.Column(db.Integer, primary_key=True)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)
    event_type = db.Column(db.String(30), nullable=False)
    stream = db.Column(db.String(20), nullable=True)  # 'technical' | 'artwork'
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    deliverable = db.relationship('Deliverable',
                                  backref=db.backref('preproduction_events', cascade='all, delete-orphan',
                                                     order_by='DeliverablePreproductionEvent.created_at'))
    author = db.relationship('User', foreign_keys=[author_id])

    def __repr__(self):
        return f'<DeliverablePreproductionEvent deliverable={self.deliverable_id} type={self.event_type}>'
