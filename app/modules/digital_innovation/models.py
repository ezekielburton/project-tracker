# Digital Innovation data model. Every DI table lives here, prefixed Di to
# avoid clashing with shared tables. The only outside reference is
# DiProject.linked_project_id, a read-only FK to the shared Project model;
# DI never imports the projects module itself.

from app.modules.core.shared.extensions import db
from datetime import datetime


# The 8 pipeline stages a feature moves through, in order, stored as plain
# strings. A closed feature's status is 'closed', which is not in this
# tuple: closing leaves the pipeline, it is not a 9th stage.
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

# Display labels for the stages. Use stage_label() when a board is in hand.
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

# Colour for each stage's column header and pill. Names must match the shared
# .status-pill--<name> classes in shared.css, which carry the dark-mode tints.
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

# A board's track decides whether 'management_review' reads as 'Management
# Review' (internal) or 'Client Review' (external). Set per board.
DI_PROJECT_TRACKS = ('internal', 'external')


def stage_label(stage, track='internal'):
    """Display label for a stage on a board with this track. Only
    'management_review' varies. Use this, not DI_STAGE_LABELS, whenever
    a DiProject is in hand."""
    if stage == 'management_review' and track == 'external':
        return 'Client Review'
    return DI_STAGE_LABELS.get(stage, stage)


class DiProject(db.Model):
    """One board. lifecycle is 'active' (on the sidebar), 'closed' or
    'archived' (both on the Archive screen). is_permanent marks the seeded
    OVP board, which the backend refuses to close, archive or link."""
    __tablename__ = 'di_projects'

    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.String(200), nullable=False)
    client_label      = db.Column(db.String(200), nullable=True)
    colour            = db.Column(db.String(20), nullable=True)
    client_charge     = db.Column(db.Float, nullable=True)
    lifecycle         = db.Column(db.String(20), nullable=False, default='active')
    # 'internal' or 'external'; see DI_PROJECT_TRACKS.
    track             = db.Column(db.String(10), nullable=False, default='internal')
    closed_at         = db.Column(db.DateTime, nullable=True)
    is_permanent      = db.Column(db.Boolean, nullable=False, default=False)
    # SET NULL: deleting the linked Project just unlinks this board.
    linked_project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    # Read-only reference to the shared Project model.
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
    DiStepTemplate the first time the feature enters that stage (see
    step_engine.py). Steps from other stages are kept as they were left."""
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
    """Department-wide default step for a stage. Copied onto a feature when
    it first enters the stage; later edits never touch steps already copied."""
    __tablename__ = 'di_step_templates'

    id         = db.Column(db.Integer, primary_key=True)
    stage      = db.Column(db.String(30), nullable=False)
    title      = db.Column(db.String(200), nullable=False)
    details    = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<DiStepTemplate {self.id} ({self.stage}): {self.title}>'


class DiCostEntry(db.Model):
    """One dated line in a project's cost ledger. 'dev_time' entries carry a
    feature and hours, priced at DiSetting.dev_hourly_rate when saved (not as
    of `date`). Other types are project-level, with di_feature_id null."""
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
    """Single-row department settings. Always read through
    lib/costs.get_settings(), which creates the row if missing."""
    __tablename__ = 'di_settings'

    id              = db.Column(db.Integer, primary_key=True)
    dev_hourly_rate = db.Column(db.Float, nullable=False, default=0)
    # Set on the DI Settings screen (routes/templates.py::save_settings).
    currency        = db.Column(db.String(10), nullable=False, default='AED')

    def __repr__(self):
        return f'<DiSetting rate={self.dev_hourly_rate} {self.currency}>'


class DiPeriodSnapshot(db.Model):
    """A frozen month or quarter rollup. Performance reads an ended period
    from here, so later cost edits don't change it. period_key is e.g.
    '2026-09' or '2026-Q3'."""
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
    """One item on the OVP board's Incoming tray, filed through
    services/intake.py. Also used as a 'dismissed' marker for a
    FeatureRequest (source_type='feature_request', source_ref=its id)."""
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