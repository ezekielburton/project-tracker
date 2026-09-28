"""
HSE & Compliance module — data model.

One entry table for every register: shared fields are columns, the rest
lives in `data` (JSONB). Plus reference data (lists, assets, people) and
the recurring schedules behind the calendar.

No derived values are stored; see lib/computed.py.
"""

from sqlalchemy.dialects.postgresql import JSONB

from app.modules.core.shared.extensions import db


# Closed set, not an editable list: each value needs an entry in
# computed.SLA_DAYS.
SEVERITIES = ('Low', 'Medium', 'High', 'Critical')

# Closed set: "near misses per incident" is a reported metric.
EVENT_CLASSES = ('Incident', 'Near miss')

# Reference-list kinds. A new simple list is a new kind here, not a new
# table; its values are edited on the Lists & people page.
REFERENCE_KINDS = (
    'location', 'department',
    'incident_type', 'issue_type', 'compliance_type',
    'injury_type', 'body_part', 'ppe_type',
    'inspection_type', 'service_type', 'vehicle_document',
    'maintenance_type', 'pm_frequency', 'tool_category', 'condition',
    'material_category', 'unit', 'training_type', 'expense_category',
    'compliance_item',
)

# Asset kinds.
ASSET_KINDS = ('vehicle', 'machine', 'forklift', 'area')


class HseReference(db.Model):
    """Editable option lists, one table keyed by `kind`. Rows are
    deactivated, never deleted, since entries still point at them."""
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
    """A vehicle, machine, forklift or area that several registers point at."""
    __tablename__ = 'hse_assets'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)
    label = db.Column(db.String(160), nullable=False)
    ref = db.Column(db.String(80), nullable=True)  # plate, serial or asset tag
    # The maker's serial, held once here and shown on the machine registers.
    serial_no = db.Column(db.String(120), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def __repr__(self):
        return f'<HseAsset {self.kind}:{self.label}>'


class HsePerson(db.Model):
    """Anyone named on an entry (reporter, owner, subject, waiting-on).
    Needs no OVP login; `user_id` links one if they have it."""
    __tablename__ = 'hse_people'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(160), nullable=True)
    organisation = db.Column(db.String(160), nullable=True)
    is_external = db.Column(db.Boolean, nullable=False, default=False)
    # Entries may be parked on this person; parked time pauses the SLA clock.
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
    """A recurring obligation and its frequency. Occurrences are generated
    at read time, never stored."""
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


# One schedule can cover several assets, with one occurrence per asset.
hse_schedule_assets = db.Table(
    'hse_schedule_assets',
    db.Column('schedule_id', db.Integer,
              db.ForeignKey('hse_schedules.id', ondelete='CASCADE'), primary_key=True),
    db.Column('asset_id', db.Integer,
              db.ForeignKey('hse_assets.id', ondelete='CASCADE'), primary_key=True),
)


class HseEntry(db.Model):
    """One row per entry, for every register. Columns are fields shared
    across registers or foreign keys; everything else lives in `data`."""
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

    # Real foreign keys: an id inside JSONB has no referential integrity.
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

    # Who the entry is about (injured employee, driver, operator). Not the
    # same as reported_by, who filed it.
    subject_id = db.Column(
        db.Integer, db.ForeignKey('hse_people.id', ondelete='SET NULL'), nullable=True)

    # The certificate a compliance entry is about. A reference, so a rename
    # keeps its renewal history together.
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
    """A file attached to an entry; the bytes live on the NAS. `nas_path` is
    stored in full so renaming a register cannot orphan a file."""
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

    # Read by the entry modal (_entry_modal.html).
    @property
    def is_previewable(self):
        from app.modules.hse.lib.files import is_previewable
        return is_previewable(self.original_filename)
