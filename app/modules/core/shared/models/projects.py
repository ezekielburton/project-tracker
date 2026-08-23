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

    # contact_id: which Contact (a person at project.client_brand) this brief
    # is for. client_id already identifies "the company" for this project, so
    # there is no separate company_id — a second column for the same concept
    # could drift out of sync. Nullable: not every project has a contact.
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id'), nullable=True)

    brief_type = db.Column(db.String(50), nullable=True)
    project_status = db.Column(db.String(50), default='draft', nullable=True)
    held_from_status = db.Column(db.String(50), nullable=True)  # status saved before put on hold
    concept_status = db.Column(db.String(50), nullable=True)    # tracks concept through the workflow
    kv_status = db.Column(db.String(50), nullable=True)         # tracks KV through the workflow
    ckv_revision_count = db.Column(db.Integer, default=0, nullable=True)  # C&KV-specific revision counter (CCM projects only)
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

    # Sentinel the dashboard filters on to find projects awaiting a
    # management decision. The full flag data lives in DecisionFlag /
    # DecisionFlagMessage.
    decision_needed = db.Column(db.Boolean, default=False, nullable=True)
 

    # Auto-populated on creation

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Set by Designers
    lead_designer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Revision tracking
    revision_count = db.Column(db.Integer, default=0, nullable=False)

    # Approval tracking — set when CS approves the final submitted deck.
    # For C&CM POSM projects this is cascaded automatically once every channel
    # is individually approved; for Standard briefs it is set directly.
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

    # Cancel/Archive — reversible removal from active lists.
    cancel_reason = db.Column(db.Text, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Soft-delete — rare, admin-only, permanent removal from the archive
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
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
        """
        The current unresolved DecisionFlag on this project, or None. A
        project can accumulate a history of past (resolved) flags over
        time — this is always the one still open, if any. Queried
        directly rather than filtered out of the `decision_flags`
        relationship in Python, so it stays correct even when that
        relationship hasn't been eagerly loaded.
        """
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


# Project Region Class. Handles region data for projects, allowing us to specify which regions are relevant for each project.
class ProjectRegion(db.Model):
    __tablename__ = 'project_regions'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    region = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<ProjectRegion {self.region} for project {self.project_id}>'


# ProjectCustomer Class, Links projects to customers, allowing customers to be assigned to projects.  
class ProjectCustomer(db.Model):
    __tablename__ = 'project_customers'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    design_deadline = db.Column(db.Date, nullable=True)
    design_deadline_time = db.Column(db.Time, nullable=True)
    cancelled = db.Column(db.Boolean, default=False, nullable=False)
    # Cancel a single customer within a C&CM project — freezes its state
    # for invoicing, and is reversible. Same shape as Project's
    # cancel_reason/cancelled_at/cancelled_by_id. `cancelled` stays the
    # source of truth every read site filters on; these three are additive,
    # for audit/display only.
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
    """Tracks CS users added as secondary CS on a project.
    The CS lead remains the primary owner; secondary CS have full operational access."""
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
    """For C&CM projects: which regions a secondary CS has subscribed to for notifications.
    If a secondary CS has no rows here, they receive all region notifications (no filter)."""
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
    """One record per parallel POSM submission channel.
    Gulf C&CM projects have multiple concurrent channels:
      - UAE: one per ProjectCustomer (posm_customer_id set)
      - Kuwait/Qatar/Bahrain/Oman: one per country (posm_customer_id = None)
    Each channel tracks its own submission state machine independently."""
    __tablename__ = 'project_posm_channels'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    posm_country = db.Column(db.String(50), nullable=False)          # 'uae', 'kuwait', etc.
    posm_customer_id = db.Column(db.Integer, db.ForeignKey('project_customers.id'), nullable=True)  # UAE only
    status = db.Column(db.String(50), default='in_queue', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Approval tracking — set when CS approves this channel's submission.
    # Once every channel on the project is approved, the route cascades
    # project.project_status → 'approved' automatically.
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    project = db.relationship('Project', backref=db.backref('posm_channels', cascade='all, delete-orphan'))
    posm_customer = db.relationship('ProjectCustomer', foreign_keys=[posm_customer_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

    def __repr__(self):
        return f'<ProjectPosmChannel {self.posm_country} cust={self.posm_customer_id} status={self.status}>'


    # ProjectFile Class — stores reference files uploaded to a project by CS or admin
class ProjectFile(db.Model):
    __tablename__ = 'project_files'

    id = db.Column(db.Integer, primary_key=True)

    # Which project this file belongs to
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    # The name we saved the file as on disk (UUID-based, avoids collisions)
    filename = db.Column(db.String(255), nullable=False)

    # The original filename the user uploaded (shown in the UI)
    original_filename = db.Column(db.String(255), nullable=False)

    # File extension e.g. 'pdf', 'jpg'
    file_type = db.Column(db.String(20), nullable=False)

    # Who uploaded it and when
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships — cascade='all, delete-orphan' ensures files are deleted from
    # SQLAlchemy's session when the parent project is deleted, preventing NOT NULL errors
    project = db.relationship('Project', backref=db.backref('reference_files', cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def __repr__(self):
        return f'<ProjectFile {self.original_filename} project={self.project_id}>'


class SiteVisit(db.Model):
    """
    Structured record of a technical person's site visit — start/end
    times captured precisely (not a freeform note) so the dashboard can
    compute when a technical designer is out of the building.
    """
    __tablename__ = 'site_visits'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(255), nullable=True)   # location name, shown as plain text or (if location_link is set) as link text
    location_link = db.Column(db.String(500), nullable=True)   # optional maps/address URL
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref=db.backref('site_visits', cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<SiteVisit project={self.project_id} user={self.user_id}>'


class ProjectOverlaySeen(db.Model):
    """
    One row per (user, project) marking that user's first visit to the new
    Detail overlay for that project — drives "first visit defaults to
    Project Details, later visits default to Deliverables". A marker, not a log.
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
