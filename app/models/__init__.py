from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime


@login_manager.user_loader
def load_user(token):
    """
    Token format: "{user_id}:{password_fingerprint}"
    The fingerprint is the last 12 chars of the password hash.
    If the password changes, the fingerprint changes, killing all active sessions.
    """
    parts = token.split(':', 1)
    try:
        user_id = int(parts[0])
    except (ValueError, IndexError):
        return None
    user = User.query.get(user_id)
    if user is None:
        return None
    # Validate fingerprint — returns None (forces logout) if password was changed
    if len(parts) == 2 and parts[1] != user.password_hash[-12:]:
        return None
    return user

# User Class

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='designer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_conditional_reviewer = db.Column(db.Boolean, default=False)
    team = db.Column(db.String(20), nullable=True)
    nas_url = db.Column(db.String(500), nullable=True)

    # JSON string storing per-type email notification opt-outs.
    # Format: '{"new_project": false, "revision_flag": true}'
    # Missing key = enabled (default on, so existing users get everything).
    notification_prefs = db.Column(db.String(2000), nullable=True)

    # Profile page fields (added for the profile redesign)
    bio = db.Column(db.Text, nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)   # app/static/avatars/<filename>
    banner_filename = db.Column(db.String(255), nullable=True)   # app/static/banners/<filename>
    favorite_food = db.Column(db.String(100), nullable=True)
    birthday = db.Column(db.Date, nullable=True)

    # First time setup columns
    wizard_completed = db.Column(db.Boolean, default=False, nullable=False)
    avatar_step_completed = db.Column(db.Boolean, nullable=False, default=False)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        """Return a token that includes a password fingerprint.
        Flask-Login stores this in the session/cookie. Changing the password
        changes the fingerprint, which invalidates all existing sessions."""
        return f"{self.id}:{self.password_hash[-12:]}"

    def wants_notification(self, key):
        """Return True if this user wants to receive email for the given pref key.
        Defaults to True when no prefs are saved or the key is absent — so all
        existing users continue to receive every notification after the migration.
        """
        import json
        if not self.notification_prefs:
            return True
        try:
            prefs = json.loads(self.notification_prefs)
            return prefs.get(key, True)  # unknown key → enabled by default
        except (ValueError, TypeError):
            return True

    def __repr__(self):
        return f'<User {self.email}>'

# Notification Class
class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    triggered_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    link = db.Column(db.String(500), nullable=True)

    # Relationships
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='notifications')
    project = db.relationship('Project', backref='notifications')
    triggered_by = db.relationship('User', foreign_keys=[triggered_by_id])

    def __repr__(self):
        return f'<Notification {self.id} for user {self.recipient_id}>'
    
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
    
class RoleTitle(db.Model):
    """
    Admin-editable "fun title" shown per role on the profile page
    (e.g. cs -> "Client Shepherd"). If a role has no row here yet,
    DEFAULT_ROLE_TITLES below is used instead — so the feature works
    out of the box before any admin edits it.
    """
    __tablename__ = 'role_titles'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False, unique=True)
    title = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<RoleTitle {self.role}: {self.title}>'


# Fallback titles — used whenever no RoleTitle row exists yet for a given role.
# Keeps the feature working immediately after this deploy, before any admin
# has visited the new "Role Titles" admin panel section to override them.
DEFAULT_ROLE_TITLES = {
    'admin': 'System Overlord',
    'cs': 'Client Shepherd',
    'designer': 'Pixel Architect',
    'team_lead': 'Design Captain',
    'management': 'The Big Picture',
}
    

class NotificationSound (db.Model):
    """
    An admin-uploaded audio file users can choose to play when a new notification arrives.
    Files themselves alive on the disk at app/static/sounds/
    This table only tracks metadata + which file backs each entry.
    """

    __tablename__ = 'notification_sounds'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # Display label
    filename = db.Column(db.String(255), nullable=False) # Actual file on disk
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def __repr__(self):
        return f'<NotificationSound {self.name}>'

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


    # Auto-populated on creation

    status = db.Column(db.String(50), default='To Be Briefed', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Set by Designers
    lead_designer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    design_start_date = db.Column(db.Date, nullable=True)

    # Hours counter
    hours_accumulated = db.Column(db.Float, default=0.0)
    timer_started_at = db.Column(db.DateTime, nullable=True)

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

    # Relationships
    cs_lead = db.relationship('User', foreign_keys=[cs_lead_id])
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

# Client class. Notes who created the client and when, for auditing purposes.
class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    contact_email = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
  

    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def __repr__(self):
        return f'<Client {self.name}>'

# Customer Class, stores customer and their region.
class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    region = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    installation_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='briefed', nullable=False)
    posm_revision_count = db.Column(db.Integer, default=0, nullable=False)

    customer = db.relationship('Customer', backref='customer_projects')
    deliverables = db.relationship('Deliverable', backref='project_customer', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ProjectCustomer project={self.project_id} customer={self.customer_id}>'
    


# Deliverable Class, represents individual deliverables within a project. 
# Flagging system for brief issues: if the brief_flag field is populated, it indicates there is an issue with the brief that needs to be resolved before work can proceed.
# The brief_flag_resolved boolean indiciates whether the issue has been resolved
# Revision comments allows CS to request revisions for deliverables and free type the feedback, which can then be viewed by designers to understand what changes are needed.
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
    brief_flag = db.Column(db.Text, nullable=True)
    brief_flag_resolved = db.Column(db.Boolean, default=False, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

    user = db.relationship('User', foreign_keys=[user_id])


# ── Status tracking logs ─────────────────────────────────────────────────
# One row per status *period*, not per change: started_at/ended_at bracket
# how long an entity sat in a given status. ended_at is NULL for exactly one
# row per entity at any time — that's the "current" period, still running.
# A transition closes the open row (sets ended_at) and opens a new one; this
# happens through the record_*_status() funnel in app/status_tracking.py,
# never as a raw assignment, so every project/customer/deliverable's full
# status history is captured in one place instead of scattered across
# every route that used to set .project_status / .status directly.
class ProjectStatusLog(db.Model):
    __tablename__ = 'project_status_logs'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    project = db.relationship('Project', backref='status_logs')
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

    project_customer = db.relationship('ProjectCustomer', backref='status_logs')
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

    deliverable = db.relationship('Deliverable', backref='status_logs')
    changed_by = db.relationship('User', foreign_keys=[changed_by_id])

    def __repr__(self):
        return f'<DeliverableStatusLog deliverable={self.deliverable_id} status={self.status} open={self.ended_at is None}>'

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
    

class ProjectSubmission(db.Model):
    __tablename__= 'project_submissions'

    id = db.Column(db.Integer, primary_key=True)

    # Which project this submission belongs to
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    # Stored filename on disk (UUID-BaseD) and the original name shown in the UI
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(10), nullable=False) # PDF or PPTX

    # Who uploaded it and when
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # True for the currently active deck - older uploads become False when replaced
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Whether concept / KV were included in this submission
    includes_concept = db.Column(db.Boolean, default=False, nullable=False)
    includes_kv = db.Column(db.Boolean, default=False, nullable=False)

    # CS Flagging - This is set when CS finds an issue with the deck
    is_flagged = db.Column(db.Boolean, default=False, nullable=False)
    flag_message = db.Column(db.Text, nullable=True)
    flagged_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    flagged_at = db.Column(db.DateTime, nullable=True)

    # Filled in when CS hits submit to Client
    submitted_to_client_at = db.Column(db.DateTime, nullable=True)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # POSM phase fields
    posm_customer_id = db.Column(db.Integer, db.ForeignKey('project_customers.id'), nullable=True)
    posm_country     = db.Column(db.String(50), nullable=True)  # 'uae','kuwait' etc. for Gulf projects
    phase = db.Column(db.String(20), default='concept_kv', nullable=False)  # 'concept_kv' or 'posm'

    # Relationships
    project = db.relationship('Project', backref=db.backref('submissions', cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
    flagged_by = db.relationship('User', foreign_keys=[flagged_by_id])
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    posm_customer = db.relationship('ProjectCustomer', foreign_keys=[posm_customer_id])

    def __repr__(self):
        return f'<ProjectSubmission {self.original_filename} project={self.project_id} active={self.is_active}>'


class ProjectRevision(db.Model):
    """Stores a revision request sent by CS back to the designer after a deck
    has been submitted to the client. Tracks the free-text notes and which
    deliverables need to be reworked."""
    __tablename__ = 'project_revisions'

    id           = db.Column(db.Integer, primary_key=True)
    project_id   = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    message      = db.Column(db.Text, nullable=False)
    sent_by_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sent_at      = db.Column(db.DateTime, default=datetime.utcnow)

    # Whether concept / KV were flagged for revision
    includes_concept = db.Column(db.Boolean, default=False, nullable=False)
    includes_kv = db.Column(db.Boolean, default=False, nullable=False)

    # POSM phase: which customer/country this revision is for (null = concept/KV phase)
    posm_customer_id = db.Column(db.Integer, db.ForeignKey('project_customers.id'), nullable=True)
    posm_country     = db.Column(db.String(50), nullable=True)  # 'uae','kuwait' etc. for Gulf projects

    project      = db.relationship('Project',
                                   backref=db.backref('revisions', cascade='all, delete-orphan',
                                                      order_by='ProjectRevision.sent_at.desc()'))
    sent_by      = db.relationship('User', foreign_keys=[sent_by_id])
    posm_customer = db.relationship('ProjectCustomer', foreign_keys=[posm_customer_id])

    def __repr__(self):
        return f'<ProjectRevision project={self.project_id} sent_at={self.sent_at}>'


class ProjectRevisionDeliverable(db.Model):
    """Junction table — links a revision request to the specific deliverables
    that CS has asked to be reworked."""
    __tablename__ = 'project_revision_deliverables'

    id             = db.Column(db.Integer, primary_key=True)
    revision_id    = db.Column(db.Integer, db.ForeignKey('project_revisions.id'), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    revision    = db.relationship('ProjectRevision',
                                  backref=db.backref('revision_deliverables', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('revision_assignments', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProjectRevisionDeliverable revision={self.revision_id} deliverable={self.deliverable_id}>'


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


class ProjectSubmissionDeliverable(db.Model):
    """Junction table — records which deliverables were included in a given submission.
    When a designer submits for internal review they select deliverables; those
    selections are stored here so CS knows what's being reviewed, and so the
    flag/revision cycle can update exactly those deliverables' statuses."""
    __tablename__ = 'project_submission_deliverables'

    id = db.Column(db.Integer, primary_key=True)

    # The submission this link belongs to
    submission_id = db.Column(db.Integer, db.ForeignKey('project_submissions.id'), nullable=False)

    # The deliverable that was included
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    # cascade ensures links are removed when the parent submission is deleted
    submission = db.relationship('ProjectSubmission',
                                 backref=db.backref('included_deliverables', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('submission_links', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProjectSubmissionDeliverable submission={self.submission_id} deliverable={self.deliverable_id}>'


class ProjectSubmissionFile(db.Model):
    """Supplementary files attached to a ProjectSubmission.

    Multiple files can be attached to the same active submission — the first
    file is on ProjectSubmission.filename as before; any additional attachments
    live here. Deleting the parent submission cascades to these rows.
    Files are stored on the NAS under the project's Submissions/ folder."""
    __tablename__ = 'project_submission_files'

    id               = db.Column(db.Integer, primary_key=True)
    submission_id    = db.Column(db.Integer, db.ForeignKey('project_submissions.id'), nullable=False)
    project_id       = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type        = db.Column(db.String(10), nullable=False)
    uploaded_by_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at      = db.Column(db.DateTime, default=datetime.utcnow)

    submission  = db.relationship('ProjectSubmission',
                                  backref=db.backref('extra_files', cascade='all, delete-orphan'))
    project     = db.relationship('Project',
                                  backref=db.backref('submission_extra_files', cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def __repr__(self):
        return f'<ProjectSubmissionFile {self.original_filename} submission={self.submission_id}>'


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
    

class BlogPost(db.Model):
    __tablename__ = 'blog_posts'

    id            = db.Column(db.Integer, primary_key=True)
    title         = db.Column(db.String(200), nullable=False)
    version_tag   = db.Column(db.String(80))
    author_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_published  = db.Column(db.Boolean, nullable=False, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    published_at  = db.Column(db.DateTime)
    sections_json = db.Column(db.Text, nullable=False, default='[]')

    author = db.relationship('User', backref='blog_posts')

    def sections(self):
        import json
        data = json.loads(self.sections_json or '[]')
        return [_BlogSection(s) for s in data]

    def __repr__(self):
        return f'<BlogPost {self.title}>'


class _BlogSection:
    def __init__(self, d):
        self.anchor = d.get('anchor', '')
        self.number = d.get('number', '')
        self.title  = d.get('title', '')
        self.blocks = [_BlogBlock(b) for b in d.get('blocks', [])]


class _BlogBlock:
    def __init__(self, d):
        self.type  = d.get('type', 'body')
        self.text  = d.get('text', '')
        self.color = d.get('color')
        self.items = d.get('items', [])


class BlogComment(db.Model):
    __tablename__ = 'blog_comments'

    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('blog_posts.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    parent_id  = db.Column(db.Integer, db.ForeignKey('blog_comments.id'), nullable=True)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author  = db.relationship('User', backref='blog_comments')
    replies = db.relationship(
        'BlogComment',
        foreign_keys='BlogComment.parent_id',
        backref=db.backref('parent', remote_side='BlogComment.id'),
        lazy='select'
    )

    def __repr__(self):
        return f'<BlogComment {self.id} on post {self.post_id}>'


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

class WikiSection(db.Model):
    """
    Top level Sections in the wiki (E.G Cs View, Designer View).
    relevant_roles is a comma-separated list of the roles this secton is for
    (drives the role indicator in the viewer). Empty = relevant to everyone.
    """

    __tablename__ = 'wiki_sections'

    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(200), nullable=False, unique=True)
    relevant_roles  = db.Column(db.String(200)) #e.g cs, admin or designer/team_lead
    sort_order      = db.Column(db.Integer, default=0)
    is_published    = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    articles = db.relationship(
        'WikiArticle',
        back_populates='section',
        cascade='all, delete-orphan',
        order_by='WikiArticle.sort_order'
    )

    def __repr__(self):
        return f'<Wiki Section {self.slug}>'
    
class WikiArticle(db.Model):
    """
    A single page within a wiki section. sections_json stores content as a JSON array of block objects
    same pattern as BlogPost, supporting: body, richtext, h3, callout,
    callout-pins, list, image, video block types.
    """

    __tablename__='wiki_articles'

    id              = db.Column(db.Integer, primary_key=True)
    section_id      = db.Column(db.Integer, db.ForeignKey('wiki_sections.id'), nullable=False)
    title           = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(200), nullable=False)
    sections_json    = db.Column(db.Text)
    sort_order      = db.Column(db.Integer, default=0)
    is_published    = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    section      = db.relationship('WikiSection', back_populates='articles')

    def __repr__(self):
        return f'<WikiArticle {self.slug} in section {self.section_id}>'


# ═══════════════════════════════════════════════════════════════════════
# Achievement system (gamification) — added 3 Jul 2026
# Six new tables, no changes to any existing table. Registered here so
# create_tables.py picks them up automatically (same as NotificationSound
# and RoleTitle above) — no separate migration script needed since none
# of this touches an existing table's columns.
# ═══════════════════════════════════════════════════════════════════════

class AchievementCategory(db.Model):
    """
    Groups related achievements together for display (e.g. "Submissions",
    "Quality", "Community"). Purely organizational — has no effect on
    whether an achievement can be earned.
    """
    __tablename__ = 'achievement_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=True)        # emoji or icon reference shown next to the category name
    display_order = db.Column(db.Integer, default=0)       # controls sort order in the admin panel + profile page

    def __repr__(self):
        return f'<AchievementCategory {self.name}>'


class AchievementBorder(db.Model):
    """
    A selectable decorative border style for the profile banner. css_class
    must match a real class defined in achievements.css — this table only
    stores the *name* of that class, not any actual styling, so adding a
    new border is: write the CSS class, then register it here via the
    admin panel (Phase 7).
    """
    __tablename__ = 'achievement_borders'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)       # admin-facing label, e.g. "Golden Shimmer"
    css_class = db.Column(db.String(100), nullable=False)  # e.g. "border-golden-shimmer" — must exist in achievements.css

    def __repr__(self):
        return f'<AchievementBorder {self.name}>'


class Achievement(db.Model):
    """
    The catalogue of achievements admins define — this table describes
    what CAN be earned, not who has earned it (see UserAchievement below
    for that). trigger_event is a free-text string matched against the
    event_type argument passed into check_achievements() in
    app/achievements.py — e.g. 'project_submitted', 'user_login'. There is
    intentionally no foreign key or enum constraining trigger_event: new
    event types can be wired up in code without a schema change, at the
    cost of a typo here silently meaning "this achievement never fires."
    """
    __tablename__ = 'achievements'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('achievement_categories.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    trigger_event = db.Column(db.String(100), nullable=False)
    threshold = db.Column(db.Integer, nullable=False, default=1)   # progress needed to earn (e.g. 10 submissions)
    is_hidden = db.Column(db.Boolean, default=False)               # shows as "???" until earned, see profile card
    badge_image = db.Column(db.String(255), nullable=True)         # filename in app/static/achievements/
    badge_type = db.Column(db.String(20), default='static')        # 'static' (<img>) or 'animated' (CSS class)
    reward_title = db.Column(db.String(100), nullable=True)        # optional fun title unlocked alongside the badge
    title_animated = db.Column(db.Boolean, default=False)
    border_id = db.Column(db.Integer, db.ForeignKey('achievement_borders.id'), nullable=True)
    display_order = db.Column(db.Integer, default=0)

    # foreign_keys= spelled out explicitly on both relationships below,
    # matching the style already used for NotificationSound.uploaded_by —
    # avoids SQLAlchemy needing to guess which FK a relationship refers to.
    category = db.relationship('AchievementCategory', foreign_keys=[category_id])
    border = db.relationship('AchievementBorder', foreign_keys=[border_id])

    def __repr__(self):
        return f'<Achievement {self.name} ({self.trigger_event} >= {self.threshold})>'


class UserAchievement(db.Model):
    """
    Tracks one user's progress toward one achievement. A row is created
    the first time check_achievements() sees a matching event for a user
    who doesn't have one yet (progress starts at 0 or 1 depending on how
    that call is made — see app/achievements.py for the exact upsert
    logic). earned_at stays NULL until progress >= the achievement's
    threshold, at which point it's stamped once and never changed again.
    """
    __tablename__ = 'user_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievements.id'), nullable=False)
    progress = db.Column(db.Integer, default=0)
    earned_at = db.Column(db.DateTime, nullable=True)

    # A user can only have ONE progress row per achievement — without this,
    # a race condition in the upsert logic could create duplicate rows that
    # each partially track progress, undercounting the real total.
    __table_args__ = (
        db.UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
    achievement = db.relationship('Achievement', foreign_keys=[achievement_id])

    def __repr__(self):
        earned = 'earned' if self.earned_at else f'{self.progress} progress'
        return f'<UserAchievement user={self.user_id} achievement={self.achievement_id} ({earned})>'


class UserDisplaySettings(db.Model):
    """
    One row per user (enforced via unique=True on user_id, not a composite
    key — there's only ever one "current" set of display choices, unlike
    UserPinnedAchievement below which is deliberately one-row-per-slot).
    Each of the three fields points at something the user has actually
    earned; the admin panel / settings page (Phase 5) is responsible for
    only ever offering earned items as choices, but this table doesn't
    enforce that itself the DB constraint.
    """
    __tablename__ = 'user_display_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # Points at a UserAchievement (not an Achievement directly) — this is
    # deliberate: it ties the active badge/title to a *specific earned
    # instance*, so if the underlying Achievement were ever deleted by an
    # admin, the FK naturally has nothing valid to point at, rather than
    # silently displaying a badge/title the user never actually earned.
    active_badge_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=True)
    active_title_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=True)
    active_border_id = db.Column(db.Integer, db.ForeignKey('achievement_borders.id'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<UserDisplaySettings user={self.user_id}>'


class UserPinnedAchievement(db.Model):
    """
    Up to 5 achievements a user has chosen to feature at the top of their
    profile card (Phase 4/5). One row per pinned slot, rather than a
    single row with 5 columns — this makes "drag to reorder" a matter of
    updating pin_order values, and "unpin one" a single DELETE, instead of
    shuffling values between fixed columns.
    """
    __tablename__ = 'user_pinned_achievements'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_achievement_id = db.Column(db.Integer, db.ForeignKey('user_achievements.id'), nullable=False)
    pin_order = db.Column(db.Integer, nullable=False)   # 1-5, controls left-to-right display order

    # A user can't pin two different achievements into the same slot —
    # this is what makes "drag to reorder" safe to implement as a delete
    # and re-insert rather than needing careful in-place slot-swapping logic.
    __table_args__ = (
        db.UniqueConstraint('user_id', 'pin_order', name='uq_user_pin_order'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
    user_achievement = db.relationship('UserAchievement', foreign_keys=[user_achievement_id])

    def __repr__(self):
        return f'<UserPinnedAchievement user={self.user_id} slot={self.pin_order}>'
