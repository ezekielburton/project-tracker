from app.modules.core.shared.extensions import db
from datetime import datetime


class ProjectSubmission(db.Model):
    __tablename__= 'project_submissions'

    id = db.Column(db.Integer, primary_key=True)

    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    # Stored filename on disk and the original name shown in the UI
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(10), nullable=False) # PDF or PPTX

    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # True for the active deck; set False when replaced
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Whether concept / KV were included in this submission
    includes_concept = db.Column(db.Boolean, default=False, nullable=False)
    includes_kv = db.Column(db.Boolean, default=False, nullable=False)

    # Set when CS flags an issue with the deck
    is_flagged = db.Column(db.Boolean, default=False, nullable=False)
    flag_message = db.Column(db.Text, nullable=True)
    flagged_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    flagged_at = db.Column(db.DateTime, nullable=True)

    # Set when CS submits to the client
    submitted_to_client_at = db.Column(db.DateTime, nullable=True)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # POSM phase fields
    posm_customer_id = db.Column(db.Integer, db.ForeignKey('project_customers.id'), nullable=True)
    posm_country     = db.Column(db.String(50), nullable=True)  # 'uae','kuwait' etc. for Gulf projects
    phase = db.Column(db.String(20), default='concept_kv', nullable=False)  # 'concept_kv' or 'posm'
    workflow_status = db.Column(db.String(30), nullable=True)
    last_internal_review_notified_at = db.Column(db.DateTime, nullable=True)
    cs_note = db.Column(db.Text, nullable=True)
    # Times a client-approved submission's file was replaced without a revision cycle.
    post_approval_edit_count = db.Column(db.Integer, default=0, nullable=False)

    # Set while a designer edits a submission in internal_review; the
    # workflow_status stays put. Cleared on re-submit for review.
    is_being_edited = db.Column(db.Boolean, default=False, nullable=False)
    editing_started_at = db.Column(db.DateTime, nullable=True)

    project = db.relationship('Project', backref=db.backref('submissions', cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
    flagged_by = db.relationship('User', foreign_keys=[flagged_by_id])
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    posm_customer = db.relationship('ProjectCustomer', foreign_keys=[posm_customer_id])

    def __repr__(self):
        return f'<ProjectSubmission {self.original_filename} project={self.project_id} active={self.is_active}>'


class ProjectSubmissionDeliverable(db.Model):
    """Which deliverables a submission covers, chosen by the designer on submit.
    The flag/revision cycle updates exactly these deliverables."""
    __tablename__ = 'project_submission_deliverables'

    id = db.Column(db.Integer, primary_key=True)

    submission_id = db.Column(db.Integer, db.ForeignKey('project_submissions.id'), nullable=False)

    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    submission = db.relationship('ProjectSubmission',
                                 backref=db.backref('included_deliverables', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('submission_links', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProjectSubmissionDeliverable submission={self.submission_id} deliverable={self.deliverable_id}>'


class ProjectSubmissionFile(db.Model):
    """Extra files on a ProjectSubmission (the first file is on
    ProjectSubmission.filename). Stored on the NAS under the project's
    Submissions/ folder."""
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
    # 'cache' = in the local draft cache, not yet on the NAS.
    # 'nas'   = on the NAS (zipped at Submit to Client, or uploaded after submission).
    storage_location = db.Column(db.String(10), default='nas', nullable=False)
    local_cache_path = db.Column(db.String(500), nullable=True)
    # One per active draft (app-enforced, no DB constraint). This file gets the
    # generated name when the draft is zipped to the NAS.
    is_main_deck     = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<ProjectSubmissionFile {self.original_filename} submission={self.submission_id}>'


class ProjectSubmissionEvent(db.Model):
    """Append-only log of actions on one submission, shown as a flat timeline.
    `message` may be rich HTML with inline images. ProjectRevision is the
    separate record of a revision requested after the client saw the deck."""
    __tablename__ = 'project_submission_events'

    id            = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('project_submissions.id'), nullable=False)
    event_type    = db.Column(db.String(30), nullable=False)  # 'submitted_for_review' | 'edited' | 'internal_revision' | 'submitted_to_client' | 'client_revision' | 'client_approval'
    author_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message       = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    submission = db.relationship('ProjectSubmission',
                                 backref=db.backref('events', cascade='all, delete-orphan',
                                                    order_by='ProjectSubmissionEvent.created_at'))
    author = db.relationship('User', foreign_keys=[author_id])

    def __repr__(self):
        return f'<ProjectSubmissionEvent submission={self.submission_id} type={self.event_type}>'


class ProjectSubmissionEventDeliverable(db.Model):
    """Which deliverables a 'client_approval' event covered, so a submission
    approved in several batches keeps a note and deliverable list per batch."""
    __tablename__ = 'project_submission_event_deliverables'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('project_submission_events.id'), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    event = db.relationship('ProjectSubmissionEvent',
                            backref=db.backref('deliverable_links', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('approval_event_links', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProjectSubmissionEventDeliverable event={self.event_id} deliverable={self.deliverable_id}>'


class ProjectRevision(db.Model):
    """A revision CS sends back to the designer after the deck went to the
    client."""
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
    """A deliverable CS asked to be reworked in a revision."""
    __tablename__ = 'project_revision_deliverables'

    id             = db.Column(db.Integer, primary_key=True)
    revision_id    = db.Column(db.Integer, db.ForeignKey('project_revisions.id'), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    revision    = db.relationship('ProjectRevision',
                                  backref=db.backref('revision_deliverables', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('revision_assignments', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProjectRevisionDeliverable revision={self.revision_id} deliverable={self.deliverable_id}>'


class TechnicalSubmission(db.Model):
    """One uploaded technical file for a deliverable, with its own internal
    review. Independent of ProjectSubmission and project_status. One row per
    upload: the newest row per deliverable is current, older rows are history.
    """
    __tablename__ = 'technical_submissions'

    id = db.Column(db.Integer, primary_key=True)

    # project_id is stored too so per-project queries skip the deliverables join.
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    # Generated filename (e.g. "Technical Drawing - Acme Rebrand - Initial.pdf")
    # and its lowercase extension without the dot.
    original_filename = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)

    # The uploader; flag/approve have their own actor fields below.
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Lifecycle state for this row. One of:
    #   'uploaded'            -> file is on the NAS, not yet sent for review
    #   'internal_review'     -> designer/team lead explicitly submitted it
    #   'internal_revision'   -> CS/admin/management flagged it, back to designer
    #   'internally_approved' -> terminal state, signed off internally
    status = db.Column(db.String(50), nullable=False, default='uploaded')

    # Set only when status == 'internal_revision'.
    flag_message = db.Column(db.Text, nullable=True)
    flagged_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    flagged_at = db.Column(db.DateTime, nullable=True)

    # Set only when status == 'internally_approved' (terminal).
    internally_approved_at = db.Column(db.DateTime, nullable=True)
    internally_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # --- Relationships -------------------------------------------------
    # ORM cascade mirrors the DB's ON DELETE CASCADE (set in the migration).
    project = db.relationship('Project', backref=db.backref('technical_submissions', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('technical_submissions', cascade='all, delete-orphan'))

    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
    flagged_by = db.relationship('User', foreign_keys=[flagged_by_id])
    internally_approved_by = db.relationship('User', foreign_keys=[internally_approved_by_id])

    def __repr__(self):
        return f'<TechnicalSubmission {self.original_filename} deliverable={self.deliverable_id} status={self.status}>'
