from app.modules.core.shared.extensions import db
from datetime import datetime


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
    # Explicit workflow lifecycle — see Projects Redesign Architecture.md §C.
    # Backfilled from existing signals in a dedicated follow-up script (not
    # yet run) rather than assumed correct from this column definition alone.
    workflow_status = db.Column(db.String(30), nullable=True)
    last_internal_review_notified_at = db.Column(db.DateTime, nullable=True)
    cs_note = db.Column(db.Text, nullable=True)
    # Post-Approval Edits: incremented each time an already-Client-Approved
    # submission's file is replaced without going through a full revision
    # cycle. Stored counter, same convention as revision_count/
    # posm_revision_count/ckv_revision_count elsewhere in this model.
    post_approval_edit_count = db.Column(db.Integer, default=0, nullable=False)

    # Set while a designer is mid-fix after clicking "Edit" on an already-
    # locked (workflow_status='internal_review') submission — a modifier on
    # top of that phase, not a new phase itself, since CS already knows to
    # look and shouldn't be silently un-notified by an edit in progress.
    # Cleared when the designer re-submits for review. The later SSE work
    # (M4) will watch this to show CS a live "currently being edited" marker.
    is_being_edited = db.Column(db.Boolean, default=False, nullable=False)
    editing_started_at = db.Column(db.DateTime, nullable=True)

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


class ProjectSubmissionEvent(db.Model):
    """Append-only history log for one submission's internal-review cycle —
    M3 Step 4 sub-step 6 (Submit for Review / Edit / Flag Internal Revision).

    One row per action: a designer's optional note when first submitting
    for review, a designer's required reason when editing an already-locked
    submission, or CS's required message (rich HTML, may include inline
    images via the existing rich-editor.js / /inline-image route) when
    flagging an internal revision. Rendered as a flat timeline — same
    pattern as the Dashboard's .decision-flag-thread, not the nested
    .flag-thread reply system, since this is a straight append-only log
    with no replies-to-replies.

    Distinct from ProjectRevision just above, which is a separate, later
    concept: a revision CS sends back to the designer *after* a deck has
    already gone to the client (M3 Step 4 sub-step 8 territory), not this
    pre-client internal-review loop."""
    __tablename__ = 'project_submission_events'

    id            = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('project_submissions.id'), nullable=False)
    event_type    = db.Column(db.String(30), nullable=False)  # 'submitted_for_review' | 'edited' | 'internal_revision'
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
    """Junction table — records which deliverables were part of a given
    ProjectSubmissionEvent. Currently only used for event_type='client_approval'
    (Mark Approved): CS's note about that batch lives on the event's own
    message column, this table just says which deliverables it covered, so a
    submission approved in several separate batches keeps a distinct note +
    deliverable list per batch rather than one note being overwritten. Same
    shape as ProjectSubmissionDeliverable, just pointed at the event instead
    of the submission itself."""
    __tablename__ = 'project_submission_event_deliverables'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('project_submission_events.id'), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    event = db.relationship('ProjectSubmissionEvent',
                            backref=db.backref('deliverable_links', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('approval_event_links', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ProjectSubmissionEventDeliverable event={self.event_id} deliverable={self.deliverable_id}>'


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
    # Draft-stage cache tracking (M3 Step 4 — Submissions content build).
    # 'cache' = sitting in the local draft-cache folder, not yet on the NAS.
    # 'nas'   = confirmed on the NAS (either zipped at Submit to Client, or
    #           a post-submission "Attach Supporting File" upload, which
    #           always goes straight to 'nas' and never touches the cache).
    storage_location = db.Column(db.String(10), default='nas', nullable=False)
    local_cache_path = db.Column(db.String(500), nullable=True)
    # Exactly one file per active draft can be True at a time (app-enforced,
    # not a DB constraint — same pattern as "only one active draft per
    # channel"). Decides which file gets the canonical auto-generated name
    # when the draft is zipped and moved to the NAS.
    is_main_deck     = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<ProjectSubmissionFile {self.original_filename} submission={self.submission_id}>'


class TechnicalSubmission(db.Model):
    """A single uploaded technical file (drawing/CAD/etc.) for one deliverable,
    and its own internal review cycle.

    This is a DELIBERATELY SEPARATE track from ProjectSubmission (the design-tab
    submission flow) and from project.project_status. A project can be, say,
    'in_progress' on the design side while its technical drawings are sitting
    in 'internal_review' here — the two never read or write each other's state.

    A deliverable accumulates one row per upload over time (initial upload,
    then one new row per revision cycle) rather than being edited in place —
    this is what makes the "submission history" list in the UI possible: the
    newest row for a given deliverable_id is its current status, and every
    older row for that same deliverable_id is history.
    """
    __tablename__ = 'technical_submissions'

    id = db.Column(db.Integer, primary_key=True)

    # Which project and deliverable this file belongs to. Both are stored
    # (not just deliverable_id) so a "give me every technical submission for
    # this project" query doesn't need to join through deliverables first —
    # same reasoning ProjectSubmissionFile uses for storing project_id
    # alongside submission_id.
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    deliverable_id = db.Column(db.Integer, db.ForeignKey('deliverables.id'), nullable=False)

    # The auto-generated filename (e.g. "Technical Drawing - Acme Rebrand -
    # Initial.pdf" or "... - Revision 2.dwg") and its lowercase extension
    # without the dot (e.g. "pdf", "dwg") — same shape as
    # ProjectSubmission.original_filename / file_type.
    original_filename = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)

    # Who uploaded this specific file, and when. Every row keeps its own
    # uploader — this does NOT get overwritten on flag/approve, since those
    # actions are performed by a different person (CS/admin/management) and
    # need their own separate actor + timestamp fields below.
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Lifecycle state for this row. One of:
    #   'uploaded'            -> file is on the NAS, not yet sent for review
    #   'internal_review'     -> designer/team lead explicitly submitted it
    #   'internal_revision'   -> CS/admin/management flagged it, back to designer
    #   'internally_approved' -> terminal state, signed off internally
    # This column is intentionally unrelated to ProjectSubmission.status and
    # to project.project_status — see the class docstring above.
    status = db.Column(db.String(50), nullable=False, default='uploaded')

    # Only meaningful when status == 'internal_revision': the free-text
    # explanation of what needs to change, plus who flagged it and when.
    # Left NULL for every other status/row.
    flag_message = db.Column(db.Text, nullable=True)
    flagged_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    flagged_at = db.Column(db.DateTime, nullable=True)

    # Only meaningful when status == 'internally_approved': who approved it
    # internally and when. This is a terminal state — nothing in this feature
    # currently moves a row out of 'internally_approved' once set.
    internally_approved_at = db.Column(db.DateTime, nullable=True)
    internally_approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # --- Relationships -------------------------------------------------
    # backref='technical_submissions' on both Project and Deliverable lets
    # existing code do project.technical_submissions / deliverable.technical_submissions
    # without needing a new query helper. cascade='all, delete-orphan' means
    # deleting a project or a deliverable automatically deletes its technical
    # submissions too, mirroring the ON DELETE CASCADE set at the DB level in
    # migrations/add_technical_submissions.py (belt-and-braces: the DB-level
    # cascade protects raw SQL/other tools, this ORM-level cascade protects
    # anything done through SQLAlchemy that hasn't flushed yet).
    project = db.relationship('Project', backref=db.backref('technical_submissions', cascade='all, delete-orphan'))
    deliverable = db.relationship('Deliverable', backref=db.backref('technical_submissions', cascade='all, delete-orphan'))

    # Three separate User relationships because three different people can
    # be involved in one row's lifecycle: whoever uploaded it, whoever
    # flagged it (if flagged), whoever internally approved it (if approved).
    # foreign_keys=[...] is required on all three since there's more than one
    # FK to the same 'users' table on this model — without it SQLAlchemy
    # can't tell which column each relationship should join on.
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
    flagged_by = db.relationship('User', foreign_keys=[flagged_by_id])
    internally_approved_by = db.relationship('User', foreign_keys=[internally_approved_by_id])

    def __repr__(self):
        return f'<TechnicalSubmission {self.original_filename} deliverable={self.deliverable_id} status={self.status}>'
