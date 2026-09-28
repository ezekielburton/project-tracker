from app.modules.core.shared.extensions import db
from datetime import datetime


class DesignType(db.Model):
    __tablename__ = 'design_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    team = db.Column(db.String(50), nullable=True)  # '2D', '3D', 'Technical', or None = all teams

    def __repr__(self):
        return f'<DesignType {self.name}>'


class DesignDirection(db.Model):
    __tablename__ = 'design_directions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    def __repr__(self):
        return f'<DesignDirection {self.name}>'


class Scope(db.Model):
    __tablename__ = 'scopes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Scope {self.name}>'


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)

    # Required Fields - set on creation
    name = db.Column(db.String(200), nullable=False)
    cs_lead_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client = db.Column(db.String(200), nullable=True)
    scope_id = db.Column(db.Integer, db.ForeignKey('scopes.id'), nullable=True)
    design_teams_requested = db.Column(db.String(200), nullable=True)
    importance = db.Column(db.String(20), nullable=True)
    design_needed_by = db.Column(db.Date, nullable=True)
    execution_date = db.Column(db.Date, nullable=True)
    job_number = db.Column(db.String(100), nullable=True, unique=True)
    value = db.Column(db.Float, nullable=True)
    brief_file = db.Column(db.String(255), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)

    # The Contact (a person at client_brand) this brief is for. client_id is
    # the company; there is no separate company_id.
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id'), nullable=True)

    brief_type = db.Column(db.String(50), nullable=True)
    project_status = db.Column(db.String(50), default='draft', nullable=True)
    held_from_status = db.Column(db.String(50), nullable=True)  # status saved before put on hold
    concept_status = db.Column(db.String(50), nullable=True)    # tracks concept through the workflow
    kv_status = db.Column(db.String(50), nullable=True)         # tracks KV through the workflow
    ckv_revision_count = db.Column(db.Integer, default=0, nullable=True)  # Concept & KV revision counter (C&CM only)
    posm_country_revision_counts = db.Column(db.JSON, nullable=True)  # {'kuwait': 2, 'qatar': 1, ...}
    campaign_notes = db.Column(db.Text, nullable=True)
    urgency = db.Column(db.String(50), nullable=True)
    required_output = db.Column(db.String(100), nullable=True)
    briefing_date = db.Column(db.Date, nullable=True)
    first_output_deadline = db.Column(db.Date, nullable=True)
    installation_date = db.Column(db.Date, nullable=True)
    last_autosaved_at = db.Column(db.DateTime, nullable=True)
    concept_deadline = db.Column(db.Date, nullable=True)
    concept_deadline_time = db.Column(db.Time, nullable=True)
    has_concept = db.Column(db.Boolean, default=False, nullable=False)
    concept_options_required = db.Column(db.Integer, nullable=True)
    has_kv = db.Column(db.Boolean, default=False, nullable=False)
    kv_deadline = db.Column(db.Date, nullable=True)
    kv_requirements = db.Column(db.Text, nullable=True)
    kv_options_required = db.Column(db.Integer, nullable=True)
    concept_designer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    kv_designer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Dashboard filter for projects awaiting a management decision; the flag
    # itself lives in DecisionFlag.
    decision_needed = db.Column(db.Boolean, default=False, nullable=True)
 

    # Auto-populated on creation

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Set by Designers
    lead_designer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Revision tracking
    revision_count = db.Column(db.Integer, default=0, nullable=False)

    # Set when CS approves the final submission. For C&CM it is set once every
    # POSM channel (and Concept/KV, if any) is approved.
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Concept & KV approval tracking (C&CM projects only)
    concept_approved_at = db.Column(db.DateTime, nullable=True)
    concept_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Standard brief fields
    design_type_id = db.Column(db.Integer, db.ForeignKey('design_types.id'), nullable=True)
    design_direction_id = db.Column(db.Integer, db.ForeignKey('design_directions.id'), nullable=True)
    client_expectation = db.Column(db.Text, nullable=True)
    what_to_avoid = db.Column(db.Text, nullable=True)

    additional_information = db.Column(db.Text, nullable=True)
    project_owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_production_only = db.Column(db.Boolean, default=False, nullable=False)
    preproduction_requirements = db.Column(db.Text, nullable=True)

    # Cancel/Archive: reversible removal from active lists.
    cancel_reason = db.Column(db.Text, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Soft-delete: admin-only, removes the project from the archive too.
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    cs_lead = db.relationship('User', foreign_keys=[cs_lead_id])
    project_owner = db.relationship('User', foreign_keys=[project_owner_id])
    cancelled_by = db.relationship('User', foreign_keys=[cancelled_by_id])
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id])
    creator = db.relationship('User', foreign_keys=[created_by_id])
    lead_designer = db.relationship('User', foreign_keys=[lead_designer_id])
    scope = db.relationship('Scope', backref='projects')
    assigned_designers = db.relationship('ProjectDesigner', backref='project', cascade='all, delete-orphan')
    client_brand = db.relationship('Client', foreign_keys=[client_id])
    project_customers = db.relationship('ProjectCustomer', backref='project_ref', cascade='all, delete-orphan')
    project_regions = db.relationship('ProjectRegion', backref='project_region_ref', cascade='all, delete-orphan')
    project_deliverables = db.relationship('Deliverable', back_populates='project', cascade='all, delete-orphan')
    concept_designer = db.relationship('User', foreign_keys=[concept_designer_id])
    kv_designer = db.relationship('User', foreign_keys=[kv_designer_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    design_type = db.relationship('DesignType', backref='projects')
    design_direction = db.relationship('DesignDirection', backref='projects')
    brief_flags = db.relationship('BriefFlag', back_populates='project', cascade='all, delete-orphan')
    decision_flags = db.relationship('DecisionFlag', back_populates='project', cascade='all, delete-orphan')
    
    @property
    def active_decision_flag(self):
        """The newest unresolved DecisionFlag, or None. Runs its own query on
        each access."""
        from app.modules.core.shared.models.flags import DecisionFlag
        return DecisionFlag.query.filter_by(
            project_id=self.id, is_resolved=False
        ).order_by(DecisionFlag.created_at.desc()).first()

    def __repr__(self):
        return f'<Project {self.name}>'


class ProjectDesigner(db.Model):
    __tablename__ = 'project_designers'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    team = db.Column(db.String(50), nullable=False)

    designer = db.relationship('User', backref ='project_assignments')

    def __repr__(self):
        return f'<ProjectDesigner ProjectID={self.project_id} DesignerID={self.user_id}>'


class ProjectReviewer(db.Model):
    __tablename__ = 'project_reviewers'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


class ProjectApproval(db.Model):
    __tablename__ = 'project_approvals'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')   # 'Approved', 'Correction Requested', 'Rejected'
    comment = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# A region a project covers.
class ProjectRegion(db.Model):
    __tablename__ = 'project_regions'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    region = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<ProjectRegion {self.region} for project {self.project_id}>'


# A customer on a project.
class ProjectCustomer(db.Model):
    __tablename__ = 'project_customers'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    design_deadline = db.Column(db.Date, nullable=True)
    design_deadline_time = db.Column(db.Time, nullable=True)
    cancelled = db.Column(db.Boolean, default=False, nullable=False)
    # Reversible cancel of one customer (freezes it for invoicing). Read sites
    # filter on `cancelled`; the three fields below are for audit/display.
    cancel_reason = db.Column(db.Text, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    installation_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='briefed', nullable=False)
    posm_revision_count = db.Column(db.Integer, default=0, nullable=False)

    customer = db.relationship('Customer', backref='customer_projects')
    deliverables = db.relationship('Deliverable', backref='project_customer', cascade='all, delete-orphan')
    cancelled_by = db.relationship('User', foreign_keys=[cancelled_by_id])

    def __repr__(self):
        return f'<ProjectCustomer project={self.project_id} customer={self.customer_id}>'


class ProjectSecondaryCS(db.Model):
    """A secondary CS on a project. The CS lead stays the owner; secondary CS
    get full operational access."""
    __tablename__ = 'project_secondary_cs'

    id           = db.Column(db.Integer, primary_key=True)
    project_id   = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    added_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    added_at     = db.Column(db.DateTime, default=datetime.utcnow)

    project   = db.relationship('Project', backref=db.backref('secondary_cs_assignments', cascade='all, delete-orphan'))
    user      = db.relationship('User', foreign_keys=[user_id], backref='secondary_cs_assignments')
    added_by  = db.relationship('User', foreign_keys=[added_by_id])

    __table_args__ = (db.UniqueConstraint('project_id', 'user_id', name='uq_project_secondary_cs'),)

    def __repr__(self):
        return f'<ProjectSecondaryCS project={self.project_id} user={self.user_id}>'


class ProjectSecondaryCsRegion(db.Model):
    """C&CM regions a secondary CS gets notifications for. No rows means all
    regions."""
    __tablename__ = 'project_secondary_cs_regions'

    id          = db.Column(db.Integer, primary_key=True)
    project_id  = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    region      = db.Column(db.String(20), nullable=False)  # 'uae', 'kuwait', 'qatar', 'bahrain', 'oman'

    project = db.relationship('Project', backref=db.backref('secondary_cs_regions', cascade='all, delete-orphan'))
    user    = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (db.UniqueConstraint('project_id', 'user_id', 'region', name='uq_project_secondary_cs_region'),)

    def __repr__(self):
        return f'<ProjectSecondaryCsRegion project={self.project_id} user={self.user_id} region={self.region}>'


class ProjectPosmChannel(db.Model):
    """One parallel POSM submission channel on a C&CM project, with its own
    status: per ProjectCustomer (posm_customer_id set) or per country
    (posm_customer_id NULL)."""
    __tablename__ = 'project_posm_channels'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    posm_country = db.Column(db.String(50), nullable=False)          # 'uae', 'kuwait', etc.
    posm_customer_id = db.Column(db.Integer, db.ForeignKey('project_customers.id'), nullable=True)  # UAE only
    status = db.Column(db.String(50), default='in_queue', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Set when this channel's deliverables are all approved. Once every channel
    # (and Concept/KV, if any) is approved, the route sets project.approved_at.
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    project = db.relationship('Project', backref=db.backref('posm_channels', cascade='all, delete-orphan'))
    posm_customer = db.relationship('ProjectCustomer', foreign_keys=[posm_customer_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

    def __repr__(self):
        return f'<ProjectPosmChannel {self.posm_country} cust={self.posm_customer_id} status={self.status}>'


    # A reference file uploaded to a project.
class ProjectFile(db.Model):
    __tablename__ = 'project_files'

    id = db.Column(db.Integer, primary_key=True)

    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    # Stored name on disk (unique, avoids collisions)
    filename = db.Column(db.String(255), nullable=False)

    # Uploaded filename, shown in the UI
    original_filename = db.Column(db.String(255), nullable=False)

    # File extension e.g. 'pdf', 'jpg'
    file_type = db.Column(db.String(20), nullable=False)

    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # delete-orphan cascade: deleting a project deletes its rows (project_id is NOT NULL).
    project = db.relationship('Project', backref=db.backref('reference_files', cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def __repr__(self):
        return f'<ProjectFile {self.original_filename} project={self.project_id}>'


class SiteVisit(db.Model):
    """
    A site visit with exact start/end times, so the dashboard can tell when a
    technical designer is out of the office.
    """
    __tablename__ = 'site_visits'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(255), nullable=True)   # shown as text, or as link text when location_link is set
    location_link = db.Column(db.String(500), nullable=True)   # optional maps/address URL
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref=db.backref('site_visits', cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<SiteVisit project={self.project_id} user={self.user_id}>'


class ProjectEditAccessRequest(db.Model):
    """An assigned designer's request for deliverable-management rights on one
    project (the overlay's "Request Editing Access"). Eligibility is computed in
    routes/project_overlay/. Grants are permanent. One row per (project, user):
    a re-request after denial resets the same row."""
    __tablename__ = 'project_edit_access_requests'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # 'pending' | 'approved' | 'denied'
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    decided_at = db.Column(db.DateTime, nullable=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    project = db.relationship('Project', backref=db.backref('edit_access_requests', cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[user_id])
    decided_by = db.relationship('User', foreign_keys=[decided_by_id])

    __table_args__ = (
        db.UniqueConstraint('project_id', 'user_id', name='uq_project_edit_access_requests_project_user'),
    )

    def __repr__(self):
        return f'<ProjectEditAccessRequest project={self.project_id} user={self.user_id} status={self.status}>'


class ProjectActivitySeen(db.Model):
    """Per-(user, project) watermarks for the Projects table's two unread dots:
    updates (ActivityLog, set on overlay open) and chat (ProjectNote, set when
    chat opens), via mark_project_activity_seen(). A missing row counts as
    seen at ACTIVITY_SEEN_ROLLOUT_CUTOFF."""
    __tablename__ = 'project_activity_seen'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    last_seen_update_at = db.Column(db.DateTime, nullable=True)
    last_seen_chat_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])
    project = db.relationship('Project', foreign_keys=[project_id])

    __table_args__ = (
        db.UniqueConstraint('user_id', 'project_id', name='uq_project_activity_seen_user_project'),
    )

    def __repr__(self):
        return f'<ProjectActivitySeen user={self.user_id} project={self.project_id}>'


class ProjectOverlaySeen(db.Model):
    """
    One row per (user, project) marking a first overlay visit. No code reads
    or writes it.
    """
    __tablename__ = 'project_overlay_views'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    first_viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
    project = db.relationship('Project', foreign_keys=[project_id])

    def __repr__(self):
        return f'<ProjectOverlaySeen user={self.user_id} project={self.project_id}>'
