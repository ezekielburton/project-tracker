"""
HSE_REGISTERS — the declaration every register is built from.

Forms, tables, filters, validation and the importer all read this, so a new
register is one entry here. A field maps to a promoted HseEntry column or
falls into `data`.

tests/test_hse_registers_contract.py checks every column name and field
type against the model, so a typo fails CI.
"""

from collections import namedtuple


# Field types the form and table renderers handle. 'time' is 'HH:MM',
# 24-hour, kept as text in `data`.
FIELD_TYPES = ('text', 'textarea', 'date', 'number', 'money', 'choice',
               'severity', 'event_class', 'person', 'asset', 'status', 'time')

# Where a register's status comes from. 'stored': the officer sets it.
# 'expiry': computed from due_at, never written. 'none': a log (mileage,
# spend, a talk held) with no workflow.
STATUS_SOURCES = ('stored', 'expiry', 'none')

# Rail groups, in rail order. A group's registers show as its sub-pages.
RAIL_GROUPS = ('daily_log', 'incidents', 'inspections', 'compliance', 'fleet',
               'machines', 'stores', 'training')


Field = namedtuple('Field', 'name label type column choices_kind required in_table')
# column, choices_kind, required, in_table
Field.__new__.__defaults__ = (None, None, False, True)

Register = namedtuple(
    'Register',
    'key label group ref_prefix status_source statuses fields schedulable '
    'default_status closed_status done_status done_requires interval_field '
    'group_by repeat_fields ledger unique_by km_due')
# schedulable is opt-in: only registers for recurring work can carry a schedule.
# default_status: a new entry's status. closed_status: saving it with no
# closed date stamps today; saving any other status clears the closed date.
# done_status: only entries at it (or with no status) count as work done;
# done_requires: fields required only at that status.
# interval_field: a choice whose label is a repeat interval; the latest entry
# per asset gets a computed next due date.
# group_by: a field the table groups rows under, paging whole groups.
# repeat_fields: carried into the next form by "Save & add another".
# ledger: stock movements in data['moves']; the balance is computed.
# unique_by: a text field no two entries may share (trimmed, any case).
# km_due: (mileage field, interval field); the latest completed entry per
# asset gets a computed next-service reading.
Register.__new__.__defaults__ = (False, None, None, None, (), None, None, (),
                                 False, None, None)


def f(name, label, type_, column=None, choices_kind=None, required=False,
      in_table=True):
    """One field. in_table=False hides it from the register table only; it
    is still in the form, still searched, and shown in the row's hover card."""
    return Field(name, label, type_, column, choices_kind, required, in_table)


DAILY_LOG = Register(
    key='daily_log',
    label='Daily log',
    group='daily_log',
    ref_prefix='DL',
    status_source='stored',
    statuses=('Open', 'Resolved'),
    default_status='Open',
    closed_status='Resolved',
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        f('location', 'Location', 'choice', column='location_id',
          choices_kind='location', required=True),
        f('description', 'What you found', 'textarea', required=True),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('reported_by', 'Logged by', 'person', column='reported_by_id', required=True),
        f('assigned_to', 'Owner', 'person', column='assigned_to_id'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Resolved date', 'date', column='closed_at', in_table=False),
    ),
)

INCIDENTS = Register(
    key='incidents',
    label='Incident & near miss',
    group='incidents',
    ref_prefix='INC',
    status_source='stored',
    statuses=('Open', 'In Progress', 'Escalated', 'Resolved'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        # Incident vs near miss, kept separate from incident_type (the cause).
        f('event_class', 'Incident or near miss', 'event_class', required=True),
        f('location', 'Location', 'choice', column='location_id',
          choices_kind='location', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department', in_table=False),
        f('incident_type', 'Incident type', 'choice',
          choices_kind='incident_type', required=True),
        f('description', 'What happened', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('reported_by', 'Reported by', 'person', column='reported_by_id', required=True, in_table=False),
        f('assigned_to', 'Owner', 'person', column='assigned_to_id'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Resolution date', 'date', column='closed_at', in_table=False),
    ),
)

GENERAL_INSPECTION = Register(
    key='general_inspection',
    label='General inspection',
    group='inspections',
    ref_prefix='INS',
    schedulable=True,
    status_source='stored',
    statuses=('Open', 'In Progress', 'Closed'),
    fields=(
        f('entry_date', 'Date of inspection', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        # "Area" here and "Location" on incidents share one list of places.
        f('location', 'Area', 'choice', column='location_id',
          choices_kind='location', required=True),
        f('reported_by', 'Inspector', 'person', column='reported_by_id', required=True, in_table=False),
        f('issue_type', 'Type of issue found', 'choice', choices_kind='issue_type'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('assigned_to', 'Reported to', 'person', column='assigned_to_id'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at', in_table=False),
    ),
)

COMPLIANCE_RENEWAL = Register(
    key='compliance_renewal',
    label='Compliance & renewal',
    group='compliance',
    ref_prefix='COM',
    # Valid / Expiring soon / Expired is computed from the expiry date.
    status_source='expiry',
    statuses=(),
    fields=(
        f('item', 'Compliance item', 'choice', column='compliance_item_id',
          choices_kind='compliance_item', required=True),
        f('compliance_type', 'Type', 'choice', choices_kind='compliance_type'),
        f('entry_date', 'Issue date', 'date', column='entry_date', required=True),
        f('due_at', 'Expiry date', 'date', column='due_at', required=True),
        f('assigned_to', 'Responsible person', 'person', column='assigned_to_id'),
    ),
)


# ---------------------------------------------------------------- incidents

FIRST_AID = Register(
    key='first_aid',
    label='First aid',
    group='incidents',
    ref_prefix='FA',
    status_source='stored',
    statuses=('Open', 'Closed'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department', in_table=False),
        f('injury_type', 'Injury type', 'choice', choices_kind='injury_type',
          required=True),
        f('treatment', 'Treatment given', 'textarea'),
        f('reported_by', 'Treated by', 'person', column='reported_by_id', required=True, in_table=False),
        # No "follow-up required" field: an open case is the follow-up.
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at', in_table=False),
    ),
)

PPE_NON_CONFORMITY = Register(
    key='ppe_non_conformity',
    label='PPE non-conformity',
    group='incidents',
    # 'PPE' is taken by the PPE register.
    ref_prefix='PNC',
    status_source='stored',
    statuses=('Open', 'In Progress', 'Closed'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department', in_table=False),
        f('ppe_type', 'PPE type', 'choice', choices_kind='ppe_type', required=True),
        f('description', 'What was wrong', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('corrective_action', 'Corrective action', 'textarea', in_table=False),
        f('assigned_to', 'Owner', 'person', column='assigned_to_id'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at', in_table=False),
    ),
)

LOST_TIME_INJURY = Register(
    key='lost_time_injury',
    label='Lost time injury',
    group='incidents',
    ref_prefix='LTI',
    status_source='stored',
    statuses=('Open', 'Closed'),
    fields=(
        f('entry_date', 'Date of injury', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department', in_table=False),
        f('description', 'Injury description', 'textarea'),
        f('body_part', 'Body part affected', 'choice', choices_kind='body_part',
          required=True),
        # Uses the shared severity scale (it drives the SLA clock), so a
        # fatality is recorded as Critical.
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('status', 'Status', 'status', column='status', required=True),
        # Days lost is computed as closed_at - entry_date.
        f('closed_at', 'Return to work date', 'date', column='closed_at'),
    ),
)

# -------------------------------------------------------------- inspections

VEHICLE_INSPECTION = Register(
    key='vehicle_inspection',
    label='Vehicle inspection',
    group='inspections',
    ref_prefix='VIN',
    schedulable=True,
    status_source='stored',
    statuses=('Open', 'In Progress', 'Closed'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        # Plate and make/model both come from the asset record.
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('subject', 'Driver', 'person', column='subject_id'),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department', in_table=False),
        f('inspection_type', 'Inspection type', 'choice',
          choices_kind='inspection_type', required=True),
        f('issues_found', 'Issues found', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('reported_by', 'Inspector', 'person', column='reported_by_id', required=True, in_table=False),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at', in_table=False),
    ),
)

FORKLIFT_INSPECTION = Register(
    key='forklift_inspection',
    label='Forklift inspection',
    group='inspections',
    ref_prefix='FLK',
    schedulable=True,
    status_source='stored',
    statuses=('Open', 'In Progress', 'Closed'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        f('asset', 'Forklift', 'asset', column='asset_id', required=True),
        f('subject', 'Operator', 'person', column='subject_id'),
        f('checklist', 'Checklist summary', 'text', in_table=False),
        f('issues_found', 'Issues found', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('reported_by', 'Inspector', 'person', column='reported_by_id', required=True, in_table=False),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at', in_table=False),
    ),
)

# -------------------------------------------------------------------- fleet

VEHICLE_SERVICE = Register(
    key='vehicle_service',
    label='Vehicle service',
    group='fleet',
    ref_prefix='SRV',
    # Next service due is derived from mileage at service plus the interval,
    # so it is not stored, and this register is not schedulable.
    status_source='stored',
    statuses=('Scheduled', 'Completed'),
    km_due=('mileage_at_service', 'service_interval'),
    fields=(
        f('entry_date', 'Service date', 'date', column='entry_date', required=True),
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('service_type', 'Service type', 'choice', choices_kind='service_type',
          required=True),
        f('mileage_at_service', 'Mileage at service (km)', 'number'),
        f('service_interval', 'Service interval (km)', 'number', in_table=False),
        f('cost', 'Cost (AED)', 'money'),
        f('reported_by', 'Logged by', 'person', column='reported_by_id', in_table=False),
        f('status', 'Status', 'status', column='status', required=True),
    ),
)

VEHICLE_REG_INSURANCE = Register(
    key='vehicle_reg_insurance',
    label='Reg & insurance',
    group='fleet',
    ref_prefix='VRI',
    # One entry per document (registration, insurance), since an entry has
    # a single due_at.
    status_source='expiry',
    statuses=(),
    fields=(
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('document_type', 'Document', 'choice', choices_kind='vehicle_document',
          required=True),
        f('provider', 'Issuer / insurer', 'text'),
        f('policy_number', 'Policy or document no.', 'text', in_table=False),
        f('entry_date', 'Issued', 'date', column='entry_date', required=True),
        f('due_at', 'Expires', 'date', column='due_at', required=True),
        f('assigned_to', 'Responsible person', 'person', column='assigned_to_id'),
    ),
)

VEHICLE_MILEAGE = Register(
    key='vehicle_mileage',
    label='Mileage',
    group='fleet',
    ref_prefix='MIL',
    # A log: no status, no filter chips. Totals are computed.
    status_source='none',
    statuses=(),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('km', 'Kilometres', 'number', required=True),
        f('odometer', 'Odometer reading (km)', 'number'),
        f('subject', 'Driver', 'person', column='subject_id'),
        f('notes', 'Notes', 'textarea', in_table=False),
    ),
)

# ----------------------------------------------------------------- machines

MACHINE_MAINTENANCE = Register(
    key='machine_maintenance',
    label='Machine maintenance',
    group='machines',
    ref_prefix='MNT',
    schedulable=True,
    status_source='stored',
    statuses=('Scheduled', 'In Progress', 'Completed', 'Overdue'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('asset', 'Machine', 'asset', column='asset_id', required=True),
        f('maintenance_type', 'Maintenance type', 'choice',
          choices_kind='maintenance_type', required=True),
        f('description', 'Description', 'textarea'),
        f('reported_by', 'Technician', 'person', column='reported_by_id', in_table=False),
        f('cost', 'Cost (AED)', 'money'),
        f('downtime_hrs', 'Downtime (hrs)', 'number'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Completed date', 'date', column='closed_at', in_table=False),
    ),
)

MACHINE_PREVENTIVE = Register(
    key='machine_preventive',
    label='Preventive maintenance',
    group='machines',
    ref_prefix='PM',
    # Status is the machine's condition. Next due comes from the last date
    # and the frequency, so this register is not schedulable.
    status_source='stored',
    statuses=('Working', 'Not Working', 'Under Maintenance'),
    interval_field='pm_frequency',
    fields=(
        f('entry_date', 'Last maintenance date', 'date', column='entry_date',
          required=True),
        f('asset', 'Machine', 'asset', column='asset_id', required=True),
        # A frequency list (Weekly, Monthly…), separate from maintenance_type.
        f('pm_frequency', 'Frequency', 'choice', choices_kind='pm_frequency'),
        f('cost', 'Cost (AED)', 'money'),
        f('notes', 'Notes', 'textarea', in_table=False),
        f('status', 'Machine status', 'status', column='status', required=True),
    ),
)

MACHINE_COST = Register(
    key='machine_cost',
    label='Machine cost',
    group='machines',
    ref_prefix='MCO',
    status_source='none',
    statuses=(),
    fields=(
        f('entry_date', 'Week ending', 'date', column='entry_date', required=True),
        f('asset', 'Machine', 'asset', column='asset_id', required=True),
        f('amount', 'Weekly spend (AED)', 'money', required=True),
        f('notes', 'Notes', 'textarea'),
    ),
)

# ------------------------------------------------------------------- stores

PPE_REGISTER = Register(
    key='ppe_register',
    label='PPE register',
    group='stores',
    ref_prefix='PPE',
    # Status is computed from the replacement date.
    status_source='expiry',
    statuses=(),
    group_by='subject',
    repeat_fields=('subject', 'department', 'entry_date'),
    fields=(
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department', in_table=False),
        f('ppe_type', 'PPE type', 'choice', choices_kind='ppe_type', required=True),
        f('entry_date', 'Issue date', 'date', column='entry_date', required=True),
        f('due_at', 'Replacement due', 'date', column='due_at', required=True),
        f('qty', 'Qty issued', 'number'),
    ),
)

TOOLS_INVENTORY = Register(
    key='tools_inventory',
    label='Tools inventory',
    group='stores',
    ref_prefix='TL',
    status_source='stored',
    statuses=('In Service', 'Under Repair', 'Decommissioned', 'Lost'),
    fields=(
        f('item', 'Tool', 'text', required=True),
        f('tool_category', 'Category', 'choice', choices_kind='tool_category'),
        f('qty', 'Quantity', 'number'),
        f('location', 'Location', 'choice', column='location_id',
          choices_kind='location'),
        f('condition', 'Condition', 'choice', choices_kind='condition'),
        f('entry_date', 'Last inspection', 'date', column='entry_date', required=True),
        f('status', 'Status', 'status', column='status', required=True),
    ),
)

MATERIAL_REQUEST = Register(
    key='material_request',
    label='Material request',
    group='stores',
    ref_prefix='MAT',
    status_source='stored',
    statuses=('Pending', 'Issued', 'Backordered', 'Rejected'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('item', 'Material', 'text', required=True),
        f('reported_by', 'Requested by', 'person', column='reported_by_id',
          required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department', in_table=False),
        f('qty_requested', 'Qty requested', 'number', required=True),
        f('qty_issued', 'Qty issued', 'number'),
        f('unit', 'Unit', 'choice', choices_kind='unit', in_table=False),
        # The whole request, not a unit price.
        f('cost', 'Cost (AED)', 'money'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Issued date', 'date', column='closed_at', in_table=False),
    ),
)

MATERIALS_IN_STOCK = Register(
    key='materials_in_stock',
    label='Materials in stock',
    group='stores',
    ref_prefix='HSM',
    # One line per material. Received, issued and counted stock are
    # movements on the line; the balance is computed (lib/stock.py).
    status_source='none',
    statuses=(),
    ledger=True,
    unique_by='item',
    fields=(
        f('item', 'Material', 'text', required=True),
        f('material_category', 'Category', 'choice', choices_kind='material_category'),
        f('unit', 'Unit', 'choice', choices_kind='unit', in_table=False),
        f('location', 'Stored at', 'choice', column='location_id',
          choices_kind='location'),
        f('reorder_level', 'Reorder level', 'number'),
        f('opening_stock', 'Opening stock', 'number', required=True, in_table=False),
        f('entry_date', 'Added', 'date', column='entry_date', required=True,
          in_table=False),
    ),
)

# ----------------------------------------------------------------- training

INDUCTION_TRAINING = Register(
    key='induction_training',
    label='Induction training',
    group='training',
    ref_prefix='TRN',
    schedulable=True,
    status_source='stored',
    statuses=('Scheduled', 'Completed', 'Cancelled', 'Overdue'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        f('training_type', 'Type of training', 'choice',
          choices_kind='training_type', required=True),
        f('topic', 'Training topic', 'text', required=True),
        f('department', 'Department trained', 'choice', column='department_id',
          choices_kind='department'),
        f('attendees', 'Attendees', 'number', required=True),
        f('reported_by', 'Trainer', 'person', column='reported_by_id', required=True),
        # Department list, but stored in JSONB, so it holds the label, not the id.
        f('trainer_department', 'Trainer department', 'choice',
          choices_kind='department', in_table=False),
        f('status', 'Status', 'status', column='status', required=True),
    ),
)

TOOLBOX_TALK = Register(
    key='toolbox_talk',
    label='Toolbox talk',
    group='training',
    ref_prefix='TBT',
    schedulable=True,
    # A talk can be planned ahead; only a completed one counts as held.
    status_source='stored',
    statuses=('Scheduled', 'Completed', 'Cancelled'),
    default_status='Completed',
    done_status='Completed',
    done_requires=('attendees',),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('entry_time', 'Time', 'time', in_table=False),
        f('topic', 'Topic', 'text', required=True),
        f('reported_by', 'Conducted by', 'person', column='reported_by_id',
          required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
        f('attendees', 'Attendees', 'number'),
        f('location', 'Location', 'choice', column='location_id',
          choices_kind='location'),
        f('status', 'Status', 'status', column='status', required=True),
        f('notes', 'Notes', 'textarea', in_table=False),
    ),
)

TRAINING_EXPENSES = Register(
    key='training_expenses',
    label='Training expenses',
    group='training',
    ref_prefix='TEX',
    status_source='none',
    statuses=(),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('expense_category', 'Category', 'choice', choices_kind='expense_category',
          required=True),
        f('description', 'Description', 'textarea'),
        f('vendor', 'Vendor / paid to', 'text'),
        f('amount', 'Amount (AED)', 'money', required=True),
        f('notes', 'Notes', 'textarea', in_table=False),
    ),
)


HSE_REGISTERS = (
    DAILY_LOG,
    # Incidents
    INCIDENTS, FIRST_AID, PPE_NON_CONFORMITY, LOST_TIME_INJURY,
    # Inspections
    GENERAL_INSPECTION, VEHICLE_INSPECTION, FORKLIFT_INSPECTION,
    # Compliance
    COMPLIANCE_RENEWAL,
    # Fleet
    VEHICLE_SERVICE, VEHICLE_REG_INSURANCE, VEHICLE_MILEAGE,
    # Machines
    MACHINE_MAINTENANCE, MACHINE_PREVENTIVE, MACHINE_COST,
    # Stores
    PPE_REGISTER, TOOLS_INVENTORY, MATERIAL_REQUEST, MATERIALS_IN_STOCK,
    # Training
    INDUCTION_TRAINING, TOOLBOX_TALK, TRAINING_EXPENSES,
)

BY_KEY = {r.key: r for r in HSE_REGISTERS}


def register(key):
    """The register declaration, or None for an unknown key."""
    return BY_KEY.get(key)


def registers_in_group(group):
    """Registers in one rail group, in declaration order."""
    return tuple(r for r in HSE_REGISTERS if r.group == group)


def table_fields(reg):
    """Fields shown as table columns, in declaration order."""
    return tuple(fl for fl in reg.fields if fl.in_table)


def jsonb_fields(reg):
    """Fields that land in HseEntry.data rather than a column."""
    return tuple(fl for fl in reg.fields if fl.column is None)


def money_fields(reg):
    """The register's money fields; its spend is their sum."""
    return tuple(fl for fl in reg.fields if fl.type == 'money')


def money_registers():
    """Registers that declare a money field, in rail order."""
    return tuple(r for r in HSE_REGISTERS if money_fields(r))


def schedulable_registers():
    """The registers a recurring schedule may point at, in rail order."""
    return tuple(r for r in HSE_REGISTERS if r.schedulable)


def asset_field(reg):
    """The register's asset field, or None. A schedule is due once per
    asset when there is one, otherwise once overall."""
    for fl in reg.fields:
        if fl.type == 'asset':
            return fl
    return None


def interval_registers():
    """Registers whose latest entry per asset has a computed next due date."""
    return tuple(r for r in HSE_REGISTERS if r.interval_field)


def counts_as_done(entry):
    """Whether an entry is work done: its register has no done_status, or
    the entry is at it. No status (filed before the register had one)
    counts as done."""
    reg = BY_KEY.get(getattr(entry, 'register', None))
    if reg is None or reg.done_status is None:
        return True
    return getattr(entry, 'status', None) in (None, reg.done_status)


def shows_asset_serial(reg):
    """Whether the register shows the picked asset's serial number: the
    machine registers, where the serial identifies the machine."""
    return reg.group == 'machines' and asset_field(reg) is not None
