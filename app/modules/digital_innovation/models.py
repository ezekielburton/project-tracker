# Digital Innovation module — data model. Self-contained: every table lives
# here (DI-prefixed to avoid clashing with the shared Project/Deliverable
# tables), per the module's Vertical Slice rules. The one exception is the
# `linked_project_id` FK below, which references the shared Project model
# read-only (for the "part of -> [project]" link) — DI never imports the
# projects feature module itself, only this one shared model.

from app.modules.core.shared.extensions import db
from datetime import datetime


# The 8 fixed pipeline stages a feature moves through, in order. Kept as a
# plain tuple (not a DB enum) to match how the rest of the app stores
# status values — see feedback.py's FeatureRequest.status for the same
# plain-string convention. A closed feature's status is the literal string
# 'closed', which is deliberately NOT in this tuple (closing is a
# transition out of the stage list, not a 9th stage). 'revision' sits
# between 'management_review' and 'implementation' — see stage_label()
# below for how 'management_review' is displayed as 'Client Review' for
# external-track boards.
DI_STAGES = (
    'researching',
    'planning',
    'coding',
    'testing',
    'optimizing',
    'management_review',
    'revision',
    'implementation',
)

# Display labels for the stages above, keyed the same way. Kept next to
# DI_STAGES so the two can never drift out of sync.
DI_STAGE_LABELS = {
    'researching': 'Researching',
    'planning': 'Planning',
    'coding': 'Coding',
    'testing': 'Testing',
    'optimizing': 'Optimizing',
    'management_review': 'Management Review',
    'revision': 'Revision',
    'implementation': 'Implementation',
}

# Colour for each stage's column header / status pill, keyed the same way.
# Names match the app's existing shared .status-pill--<name> CSS classes
# (main.css/shared.css) — reusing those instead of inventing new colours,
# per theming.md, gets dark-mode tinting for free.
DI_STAGE_COLOURS = {
    'researching': 'coral',
    'planning': 'sky',
    'coding': 'lavender',
    'testing': 'salmon',
    'optimizing': 'sage',
    'management_review': 'canary',
    'revision': 'poppy',
    'implementation': 'clover',
}

# Cost ledger entry types (DiCostEntry.type).
DI_COST_TYPES = ('dev_time', 'claude', 'hardware', 'licensing')

# A board's track decides whether its 'management_review' stage reads as
# 'Management Review' (internal work) or 'Client Review' (external/client
# work) everywhere a stage label is shown. Set once per board (DiProject.
# track), not per feature — see stage_label() below.
DI_PROJECT_TRACKS = ('internal', 'external')


def stage_label(stage, track='internal'):
    """Resolve the display label for a stage, honouring the board's
    track. Only 'management_review' varies — every other stage falls
    back to the plain DI_STAGE_LABELS entry. Any code that renders a
    stage name to a user — every call site with a real DiProject in
    hand should use this instead of indexing DI_STAGE_LABELS directly,
    so a card never shows 'Management Review' on an external board or
    vice versa.
    """
    if stage == 'management_review' and track == 'external':
        return 'Client Review'
    return DI_STAGE_LABELS.get(stage, stage)


class DiProject(db.Model):
    """One Trello-style board. lifecycle drives where it shows: 'active' on
    the module sidebar, 'closed' -> moves to Archive but keeps its data,
    'archived' is the resting state in Archive. is_permanent marks the
    seeded OVP board — the backend refuses to close/archive/delete any
    row with is_permanent=True, whatever the UI does."""
    __tablename__ = 'di_projects'

    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.String(200), nullable=False)
    client_label      = db.Column(db.String(200), nullable=True)
    colour            = db.Column(db.String(20), nullable=True)
    client_charge     = db.Column(db.Float, nullable=True)
    lifecycle         = db.Column(db.String(20), nullable=False, default='active')
    # 'internal' or 'external' — see DI_PROJECT_TRACKS / stage_label()
    # above. Board-level, not per-feature: every card on a board shares
    # its track.
    track             = db.Column(db.String(10), nullable=False, default='internal')
    closed_at         = db.Column(db.DateTime, nullable=True)
    is_permanent      = db.Column(db.Boolean, nullable=False, default=False)
    # ON DELETE SET NULL: if the linked system project is ever deleted, this
    # DI project just becomes unlinked rather than being dragged down with it.
    linked_project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    # Read-only reference to the shared Project model — see module docstring.
    linked_project = db.relationship('Project')

    features      = db.relationship('DiFeature', backref='project',
                                     cascade='all, delete-orphan',
                                     order_by='DiFeature.sort_order')
    cost_entries  = db.relationship('DiCostEntry', backref='project',
                                     cascade='all, delete-orphan')
    intake_items  = db.relationship('DiIntakeItem', backref='project',
                                     cascade='all, delete-orphan')

    def __repr__(self):
        return f'<DiProject {self.id}: {self.name}>'


class DiFeature(db.Model):
    """One card on the board. status is one of DI_STAGES, or 'closed' once
    finished. sort_order is the manual position within its column."""
    __tablename__ = 'di_features'

    id             = db.Column(db.Integer, primary_key=True)
    di_project_id  = db.Column(db.Integer, db.ForeignKey('di_projects.id'), nullable=False)
    name           = db.Column(db.String(200), nullable=False)
    status         = db.Column(db.String(30), nullable=False, default=DI_STAGES[0])
    projected_date = db.Column(db.Date, nullable=True)
    closed_at      = db.Column(db.DateTime, nullable=True)
    sort_order     = db.Column(db.Integer, nullable=False, default=0)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    steps        = db.relationship('DiFeatureStep', backref='feature',
                                    cascade='all, delete-orphan',
                                    order_by='DiFeatureStep.sort_order')
    cost_entries = db.relationship('DiCostEntry', backref='feature')

    def __repr__(self):
        return f'<DiFeature {self.id}: {self.name} ({self.status})>'


class DiFeatureStep(db.Model):
    """One checklist item on a feature, for one stage. Copied from
    DiStepTemplate when the feature enters that stage (see brain A in the
    build brief) — editing a feature's steps here never touches the
    template, and template edits only affect features entering the stage
    from then on. Steps from past stages are kept (all is_done=True), so a
    feature's full history stays visible."""
    __tablename__ = 'di_feature_steps'

    id            = db.Column(db.Integer, primary_key=True)
    di_feature_id = db.Column(db.Integer, db.ForeignKey('di_features.id'), nullable=False)
    stage         = db.Column(db.String(30), nullable=False)
    title         = db.Column(db.String(200), nullable=False)
    details       = db.Column(db.Text, nullable=True)
    is_done       = db.Column(db.Boolean, nullable=False, default=False)
    sort_order    = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<DiFeatureStep {self.id} ({self.stage}): {self.title}>'


class DiStepTemplate(db.Model):
    """Department-wide default step list for a stage — edited independently
    of any feature. Copied onto a DiFeature's steps when it enters that
    stage; editing a template afterwards never rewrites steps already
    copied."""
    __tablename__ = 'di_step_templates'

    id         = db.Column(db.Integer, primary_key=True)
    stage      = db.Column(db.String(30), nullable=False)
    title      = db.Column(db.String(200), nullable=False)
    details    = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<DiStepTemplate {self.id} ({self.stage}): {self.title}>'


class DiCostEntry(db.Model):
    """One dated ledger line for a project's cost breakdown. For type=
    'dev_time', di_feature_id is set (dev hours are tracked per-feature)
    and amount is frozen at DiSetting.dev_hourly_rate as of `date` — so a
    later rate change never rewrites a past entry's cost. For the other
    three types di_feature_id is left null; cost there is project-level."""
    __tablename__ = 'di_cost_entries'

    id            = db.Column(db.Integer, primary_key=True)
    di_project_id = db.Column(db.Integer, db.ForeignKey('di_projects.id'), nullable=False)
    date          = db.Column(db.Date, nullable=False)
    type          = db.Column(db.String(20), nullable=False)
    di_feature_id = db.Column(db.Integer, db.ForeignKey('di_features.id'), nullable=True)
    description   = db.Column(db.String(255), nullable=True)
    amount        = db.Column(db.Float, nullable=False)
    hours         = db.Column(db.Float, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DiCostEntry {self.id}: {self.type} {self.amount} on {self.date}>'


class DiSetting(db.Model):
    """Single-row department settings. Read/written through one row (no
    per-user or per-project override) — a helper in lib/ will fetch-or-
    create it, same idea as a lot of this app's singleton config rows."""
    __tablename__ = 'di_settings'

    id              = db.Column(db.Integer, primary_key=True)
    dev_hourly_rate = db.Column(db.Float, nullable=False, default=0)
    # Vitamin is Dubai-based, so AED is the sensible default — change at
    # /digital-innovation settings if that's wrong.
    currency        = db.Column(db.String(10), nullable=False, default='AED')

    def __repr__(self):
        return f'<DiSetting rate={self.dev_hourly_rate} {self.currency}>'


class DiPeriodSnapshot(db.Model):
    """A frozen month/quarter total (brain C). Once written, Performance
    reads a closed period from here instead of recomputing live, so
    editing an old cost entry can never rewrite history. period_key is
    e.g. '2026-09' for a month or '2026-Q3' for a quarter."""
    __tablename__ = 'di_period_snapshots'

    id             = db.Column(db.Integer, primary_key=True)
    period_type    = db.Column(db.String(10), nullable=False)
    period_key     = db.Column(db.String(20), nullable=False)
    snapshot_data  = db.Column(db.JSON, nullable=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('period_type', 'period_key'),)

    def __repr__(self):
        return f'<DiPeriodSnapshot {self.period_type} {self.period_key}>'


class DiIntakeItem(db.Model):
    """One approved feedback item waiting to be placed on the (permanent)
    OVP board. Created by the intake seam (services/intake.py, Phase 2) —
    this module never imports the feedback module's models, it only
    receives plain values through that function. di_project_id will always
    be the OVP board's id in practice, but isn't hard-pinned to it here so
    the column stays an ordinary FK like everything else."""
    __tablename__ = 'di_intake_items'

    id            = db.Column(db.Integer, primary_key=True)
    di_project_id = db.Column(db.Integer, db.ForeignKey('di_projects.id'), nullable=False)
    source_type   = db.Column(db.String(20), nullable=False)
    source_ref    = db.Column(db.String(100), nullable=True)
    title         = db.Column(db.String(200), nullable=False)
    description   = db.Column(db.Text, nullable=True)
    status        = db.Column(db.String(20), nullable=False, default='pending')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DiIntakeItem {self.id}: {self.title} ({self.status})>'