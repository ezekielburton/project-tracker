"""
HSE & Compliance module — data model.

One entry table for all twenty-one registers: the fields every register
shares are real columns, everything register-specific lives in `data`
(JSONB). Alongside it sit the officer's own reference data — assets,
lists, people — and the recurring schedule the calendar is built on.

Nothing here stores a derived value. Days open, days to expiry and
friends are computed at read time in lib/computed.py.
"""

from sqlalchemy.dialects.postgresql import JSONB

from app.modules.core.shared.extensions import db


# Severity is a closed set, not a list the officer edits: it drives the
# SLA clock and the performance page, so a new value would silently have
# no SLA behind it.
SEVERITIES = ('Low', 'Medium', 'High', 'Critical')

# Something that happened, or something that nearly did. A closed set
# rather than a reference list: "near misses per incident" is a reported
# metric, and a renamed value would quietly change it.
EVENT_CLASSES = ('Incident', 'Near miss')

# Reference-list kinds. A new simple list is a new kind here, not a new table.
# Everything past the first two is filled in by the officer himself on the
# Lists & people page — they need no code beyond this tuple and a label.
REFERENCE_KINDS = (
    'location', 'department',
    'incident_type', 'issue_type', 'compliance_type',
    'injury_type', 'body_part', 'ppe_type',
    'inspection_type', 'service_type', 'vehicle_document',
    'maintenance_type', 'pm_frequency', 'tool_category', 'condition',
    'material_category', 'unit', 'training_type', 'expense_category',
    'compliance_item',
)

# Asset kinds. An asset is a physical thing several registers point at.
ASSET_KINDS = ('vehicle', 'machine', 'forklift', 'area')


class HseReference(db.Model):
    """The officer's own option lists, one table keyed by `kind`. Never
    deleted — deactivated, because existing entries still point at the value."""
    __tablename__ = 'hse_reference'
    __table_args__ = (db.UniqueConstraint('kind', 'label', name='uq_hse_reference_kind_label'),)

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False, index=True)
    label = db.Column(db.String(160), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def __repr__(self):
        return f'<HseReference {self.kind}:{self.label}>'


class HseAsset(db.Model):
    """A vehicle, machine, forklift or area. Eight registers point at the
    same physical things; as free text one vehicle becomes four spellings."""
    __tablename__ = 'hse_assets'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    label = db.Column(db.String(160), nullable=False)
    ref = db.Column(db.String(80), nullable=True)  # plate, serial or asset tag
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def __repr__(self):
        return f'<HseAsset {self.kind}:{self.label}>'


class HsePerson(db.Model):
    """Anyone named on an entry — reported by, owner, or the person an
    action is waiting on. Needs no OVP login; `user_id` links one when
    they happen to have it."""
    __tablename__ = 'hse_people'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(160), nullable=True)
    organisation = db.Column(db.String(160), nullable=True)
    is_external = db.Column(db.Boolean, nullable=False, default=False)
    # When true, an entry may park on this person: that time is reported
    # separately and the SLA clock pauses while it is parked.
    can_hold_actions = db.Column(db.Boolean, nullable=False, default=False)
    email = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
    )
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<HsePerson {self.name}>'


class HseSchedule(db.Model):
    """A recurring obligation — what the site is supposed to do, and how
    often. Occurrences are generated at read time, never stored."""
    __tablename__ = 'hse_schedules'

    id = db.Column(db.Integer, primary_key=True)
    register = db.Column(db.String(40), nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    frequency = db.Column(db.String(20), nullable=False)  # daily|weekly|monthly|quarterly|annual
    interval = db.Column(db.Integer, nullable=False, default=1)
    weekday = db.Column(db.Integer, nullable=True)       # 0=Mon, for weekly
    day_of_month = db.Column(db.Integer, nullable=True)  # for monthly and longer
    starts_on = db.Column(db.Date, nullable=False)
    ends_on = db.Column(db.Date, nullable=True)
    owner_id = db.Column(
        db.Integer, db.ForeignKey('hse_people.id', ondelete='SET NULL'), nullable=True,
    )
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    owner = db.relationship('HsePerson', foreign_keys=[owner_id])
    assets = db.relationship('HseAsset', secondary='hse_schedule_assets', lazy='selectin')

    def __repr__(self):
        return f'<HseSchedule {self.register}:{self.label}>'


# One schedule can cover several assets — three vehicles inspected every
# Monday is one row, three occurrences a week.
hse_schedule_assets = db.Table(
    'hse_schedule_assets',
    db.Column('schedule_id', db.Integer,
              db.ForeignKey('hse_schedules.id', ondelete='CASCADE'), primary_key=True),
    db.Column('asset_id', db.Integer,
              db.ForeignKey('hse_assets.id', ondelete='CASCADE'), primary_key=True),
)


class HseEntry(db.Model):
    """One row per register entry, for every register. A column here earns
    its place by being shared across registers or by being a foreign key;
    everything else lives in `data`."""
    __tablename__ = 'hse_entries'
    __table_args__ = (
        db.UniqueConstraint('register', 'ref', name='uq_hse_entries_register_ref'),
        db.Index('ix_hse_entries_register_status', 'register', 'status'),
        db.Index('ix_hse_entries_register_date', 'register', 'entry_date'),
        db.Index('ix_hse_entries_due_at', 'due_at'),
        db.Index('ix_hse_entries_occurrence', 'schedule_id', 'occurrence_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    register = db.Column(db.String(40), nullable=False, index=True)
    ref = db.Column(db.String(40), nullable=False)

    entry_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(40), nullable=True)
    severity = db.Column(db.String(20), nullable=True)
    closed_at = db.Column(db.Date, nullable=True)
    due_at = db.Column(db.Date, nullable=True)

    # Foreign keys rather than JSONB values: an id inside JSONB has no
    # referential integrity and rots the first time a record is merged.
    location_id = db.Column(
        db.Integer, db.ForeignKey('hse_reference.id', ondelete='SET NULL'), nullable=True)
    department_id = db.Column(
        db.Integer, db.ForeignKey('hse_reference.id', ondelete='SET NULL'), nullable=True)
    asset_id = db.Column(
        db.Integer, db.ForeignKey('hse_assets.id', ondelete='SET NULL'), nullable=True)
    reported_by_id = db.Column(
        db.Integer, db.ForeignKey('hse_people.id', ondelete='SET NULL'), nullable=True)
    assigned_to_id = db.Column(
        db.Integer, db.ForeignKey('hse_people.id', ondelete='SET NULL'), nullable=True)

    # The person this entry is ABOUT — the injured employee, the driver,
    # the operator. Deliberately not reported_by: that is who filed it,
    # and conflating the two makes every "who reports most" answer wrong.
    subject_id = db.Column(
        db.Integer, db.ForeignKey('hse_people.id', ondelete='SET NULL'), nullable=True)

    # The certificate a compliance entry is about — a reference, not free
    # text, so renaming it keeps its renewal history instead of splitting it.
    compliance_item_id = db.Column(
        db.Integer, db.ForeignKey('hse_reference.id', ondelete='SET NULL'), nullable=True)

    # Parked with someone else. The pair is set and cleared together.
    waiting_on_id = db.Column(
        db.Integer, db.ForeignKey('hse_people.id', ondelete='SET NULL'), nullable=True)
    waiting_since = db.Column(db.Date, nullable=True)

    # Set when this entry satisfies a planned occurrence.
    schedule_id = db.Column(
        db.Integer, db.ForeignKey('hse_schedules.id', ondelete='SET NULL'), nullable=True)
    occurrence_date = db.Column(db.Date, nullable=True)

    created_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    data = db.Column(JSONB, nullable=False, server_default='{}')

    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, nullable=False,
                           server_default=db.func.now(), onupdate=db.func.now())

    location = db.relationship('HseReference', foreign_keys=[location_id])
    department = db.relationship('HseReference', foreign_keys=[department_id])
    asset = db.relationship('HseAsset', foreign_keys=[asset_id])
    reported_by = db.relationship('HsePerson', foreign_keys=[reported_by_id])
    assigned_to = db.relationship('HsePerson', foreign_keys=[assigned_to_id])
    subject = db.relationship('HsePerson', foreign_keys=[subject_id])
    compliance_item = db.relationship('HseReference', foreign_keys=[compliance_item_id])
    waiting_on = db.relationship('HsePerson', foreign_keys=[waiting_on_id])
    schedule = db.relationship('HseSchedule', foreign_keys=[schedule_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    def __repr__(self):
        return f'<HseEntry {self.ref}>'


class HseRefCounter(db.Model):
    """Per-register counter behind ref generation. Bumped by one atomic
    statement in lib/refs.py — never read-then-write."""
    __tablename__ = 'hse_ref_counters'

    register = db.Column(db.String(40), primary_key=True)
    last_value = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<HseRefCounter {self.register}={self.last_value}>'


class HseAttachment(db.Model):
    """A file filed against an entry. The bytes live on the NAS; this row is
    the record of where. `nas_path` is stored in full rather than rebuilt on
    read, so renaming a register later cannot orphan an existing file."""
    __tablename__ = 'hse_attachments'

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(
        db.Integer, db.ForeignKey('hse_entries.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    nas_path = db.Column(db.String(1000), nullable=False)
    uploaded_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    entry = db.relationship(
        'HseEntry',
        backref=db.backref('attachments', lazy='selectin', cascade='all, delete-orphan'))
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])

    def __repr__(self):
        return f'<HseAttachment {self.original_filename}>'
