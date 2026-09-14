"""
HSE_REGISTERS — the one declaration every register is built from.

Forms, tables, filters, validation and the importer all render from this,
so adding a register is one entry here rather than a feature. A field
either maps to a promoted column on HseEntry or falls into `data`.

This is a declared-contract seam: tests/test_hse_registers_contract.py
checks every column name and field type against reality, so a typo fails
CI instead of rendering a dead form.
"""

from collections import namedtuple


# Field types the form and table renderers handle.
FIELD_TYPES = ('text', 'textarea', 'date', 'number', 'money', 'choice',
               'severity', 'event_class', 'person', 'asset', 'status')

# How a register's status is arrived at. 'stored' means the officer sets
# it; 'expiry' means it is computed from due_at and nothing writes it;
# 'none' is a log — mileage, spend, a talk that happened — which has no
# workflow and must not be given a fake one.
STATUS_SOURCES = ('stored', 'expiry', 'none')

# Rail groups. The tab strip inside a group is its registers, in order.
RAIL_GROUPS = ('incidents', 'inspections', 'compliance', 'fleet',
               'machines', 'stores', 'training')


Field = namedtuple('Field', 'name label type column choices_kind required')
Field.__new__.__defaults__ = (None, None, False)  # column, choices_kind, required

Register = namedtuple(
    'Register',
    'key label group ref_prefix status_source statuses fields schedulable')
# Most registers record things as they happen. Only the ones that genuinely
# recur can carry a schedule, so it is opt-in.
Register.__new__.__defaults__ = (False,)


def f(name, label, type_, column=None, choices_kind=None, required=False):
    return Field(name, label, type_, column, choices_kind, required)


INCIDENTS = Register(
    key='incidents',
    label='Incident & near miss',
    group='incidents',
    ref_prefix='INC',
    status_source='stored',
    statuses=('Open', 'In Progress', 'Escalated', 'Resolved'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        # What kind of event it was, kept apart from what caused it — an
        # electrical near miss is still electrical. Without this split the
        # register cannot answer the question its own name asks.
        f('event_class', 'Incident or near miss', 'event_class', required=True),
        f('location', 'Location', 'choice', column='location_id',
          choices_kind='location', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
        f('incident_type', 'Incident type', 'choice',
          choices_kind='incident_type', required=True),
        f('description', 'What happened', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('reported_by', 'Reported by', 'person', column='reported_by_id', required=True),
        f('assigned_to', 'Owner', 'person', column='assigned_to_id'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Resolution date', 'date', column='closed_at'),
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
        # The workbook calls this Area on inspections and Location on
        # incidents. They are the same list of places, so they share one.
        f('location', 'Area', 'choice', column='location_id',
          choices_kind='location', required=True),
        f('reported_by', 'Inspector', 'person', column='reported_by_id', required=True),
        f('issue_type', 'Type of issue found', 'choice', choices_kind='issue_type'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('assigned_to', 'Reported to', 'person', column='assigned_to_id'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at'),
    ),
)

COMPLIANCE_RENEWAL = Register(
    key='compliance_renewal',
    label='Compliance & renewal',
    group='compliance',
    ref_prefix='COM',
    # Valid / Expiring soon / Expired is a pure function of the expiry
    # date, so it is computed and nothing writes `status` here.
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
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
        f('injury_type', 'Injury type', 'choice', choices_kind='injury_type',
          required=True),
        f('treatment', 'Treatment given', 'textarea'),
        f('reported_by', 'Treated by', 'person', column='reported_by_id', required=True),
        # The workbook's "Follow-up required? Yes/No" is dropped: an open
        # case IS the follow-up, so the two columns could disagree.
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at'),
    ),
)

PPE_NON_CONFORMITY = Register(
    key='ppe_non_conformity',
    label='PPE non-conformity',
    group='incidents',
    # Not PPE — that prefix belongs to the PPE issue register.
    ref_prefix='PNC',
    status_source='stored',
    statuses=('Open', 'In Progress', 'Closed'),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
        f('ppe_type', 'PPE type', 'choice', choices_kind='ppe_type', required=True),
        f('description', 'What was wrong', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('corrective_action', 'Corrective action', 'textarea'),
        f('assigned_to', 'Owner', 'person', column='assigned_to_id'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at'),
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
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
        f('description', 'Injury description', 'textarea'),
        f('body_part', 'Body part affected', 'choice', choices_kind='body_part',
          required=True),
        # The workbook offers Low/Medium/High/Fatality here. Severity is the
        # app-wide closed set that drives the SLA clock, so a fatality is
        # recorded as Critical rather than forking the scale.
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('status', 'Status', 'status', column='status', required=True),
        # Days lost is closed_at - entry_date, computed like every duration.
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
        # One asset field covers the workbook's Vehicle No. AND Make/Model:
        # both live on the asset record, said once.
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('subject', 'Driver', 'person', column='subject_id'),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
        f('inspection_type', 'Inspection type', 'choice',
          choices_kind='inspection_type', required=True),
        f('issues_found', 'Issues found', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('reported_by', 'Inspector', 'person', column='reported_by_id', required=True),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at'),
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
        f('asset', 'Forklift', 'asset', column='asset_id', required=True),
        f('subject', 'Operator', 'person', column='subject_id'),
        f('checklist', 'Checklist summary', 'text'),
        f('issues_found', 'Issues found', 'textarea'),
        f('severity', 'Severity', 'severity', column='severity', required=True),
        f('reported_by', 'Inspector', 'person', column='reported_by_id', required=True),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Closed date', 'date', column='closed_at'),
    ),
)

# -------------------------------------------------------------------- fleet

VEHICLE_SERVICE = Register(
    key='vehicle_service',
    label='Vehicle service',
    group='fleet',
    ref_prefix='SRV',
    # A service record is a completed event. The workbook's OK/Due status is
    # computed from mileage, not a workflow the officer drives — next-due is
    # derived from mileage at service plus the interval, so it is never
    # stored and this register never appears as a planned calendar tile.
    status_source='stored',
    statuses=('Scheduled', 'Completed'),
    fields=(
        f('entry_date', 'Service date', 'date', column='entry_date', required=True),
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('service_type', 'Service type', 'choice', choices_kind='service_type',
          required=True),
        f('mileage_at_service', 'Mileage at service (km)', 'number'),
        f('service_interval', 'Service interval (km)', 'number'),
        f('cost', 'Cost (AED)', 'money'),
        f('reported_by', 'Logged by', 'person', column='reported_by_id'),
        f('status', 'Status', 'status', column='status', required=True),
    ),
)

VEHICLE_REG_INSURANCE = Register(
    key='vehicle_reg_insurance',
    label='Reg & insurance',
    group='fleet',
    ref_prefix='VRI',
    # One entry per document, not one row per vehicle with two expiry dates:
    # there is one due_at, and splitting keeps expiry status, the calendar
    # and Compliance health working with no exception carved out here.
    status_source='expiry',
    statuses=(),
    fields=(
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('document_type', 'Document', 'choice', choices_kind='vehicle_document',
          required=True),
        f('provider', 'Issuer / insurer', 'text'),
        f('policy_number', 'Policy or document no.', 'text'),
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
    # A log. No workflow, so no status and no filter chips — see
    # STATUS_SOURCES. Totals per vehicle and per period are computed.
    status_source='none',
    statuses=(),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('asset', 'Vehicle', 'asset', column='asset_id', required=True),
        f('km', 'Kilometres', 'number', required=True),
        f('odometer', 'Odometer reading (km)', 'number'),
        f('subject', 'Driver', 'person', column='subject_id'),
        f('notes', 'Notes', 'textarea'),
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
        f('reported_by', 'Technician', 'person', column='reported_by_id'),
        f('cost', 'Cost (AED)', 'money'),
        f('downtime_hrs', 'Downtime (hrs)', 'number'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Completed date', 'date', column='closed_at'),
    ),
)

MACHINE_PREVENTIVE = Register(
    key='machine_preventive',
    label='Preventive maintenance',
    group='machines',
    ref_prefix='PM',
    # The status here is the machine's condition, which the officer sets.
    # The workbook is explicit that there is no calendar due date — PM is
    # called when a machine stops — so this register feeds no schedule.
    status_source='stored',
    statuses=('Working', 'Not Working', 'Under Maintenance'),
    fields=(
        f('entry_date', 'Last maintenance date', 'date', column='entry_date',
          required=True),
        f('asset', 'Machine', 'asset', column='asset_id', required=True),
        # The workbook's "Maintenance Type" here is a frequency (Weekly,
        # Monthly, …), not the Preventive/Corrective list next door. Two
        # different lists deserve two different kinds.
        f('pm_frequency', 'Frequency', 'choice', choices_kind='pm_frequency'),
        f('cost', 'Cost (AED)', 'money'),
        f('notes', 'Notes', 'textarea'),
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
    # Active / Due for replacement / Expired is exactly the expiry ladder,
    # so it is computed from the replacement date rather than typed.
    status_source='expiry',
    statuses=(),
    fields=(
        f('subject', 'Employee', 'person', column='subject_id', required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
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
    statuses=('In Service', 'Under Repair', 'Decommissioned'),
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
          choices_kind='department'),
        f('qty_requested', 'Qty requested', 'number', required=True),
        f('qty_issued', 'Qty issued', 'number'),
        f('status', 'Status', 'status', column='status', required=True),
        f('closed_at', 'Issued date', 'date', column='closed_at'),
    ),
)

MATERIALS_IN_STOCK = Register(
    key='materials_in_stock',
    label='Materials in stock',
    group='stores',
    ref_prefix='HSM',
    # Closing stock and the OK/Reorder flag are both arithmetic on the three
    # quantity fields, so neither is stored and neither can be a filter chip
    # yet. Low stock surfaces on the Overview instead.
    status_source='none',
    statuses=(),
    fields=(
        f('entry_date', 'As of', 'date', column='entry_date', required=True),
        f('item', 'Material', 'text', required=True),
        f('material_category', 'Category', 'choice', choices_kind='material_category'),
        f('unit', 'Unit', 'choice', choices_kind='unit'),
        f('opening_stock', 'Opening stock', 'number', required=True),
        f('received', 'Received', 'number'),
        f('issued', 'Issued', 'number'),
        f('reorder_level', 'Reorder level', 'number'),
        f('location', 'Stored at', 'choice', column='location_id',
          choices_kind='location'),
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
        f('training_type', 'Type of training', 'choice',
          choices_kind='training_type', required=True),
        f('topic', 'Training topic', 'text', required=True),
        f('department', 'Department trained', 'choice', column='department_id',
          choices_kind='department'),
        f('attendees', 'Attendees', 'number', required=True),
        f('reported_by', 'Trainer', 'person', column='reported_by_id', required=True),
        # Shares the department list but lands in JSONB, so it stores the
        # label rather than the id — the promoted-column rule, both ways.
        f('trainer_department', 'Trainer department', 'choice',
          choices_kind='department'),
        f('status', 'Status', 'status', column='status', required=True),
    ),
)

TOOLBOX_TALK = Register(
    key='toolbox_talk',
    label='Toolbox talk',
    group='training',
    ref_prefix='TBT',
    schedulable=True,
    # A talk either happened or was never logged. No workflow.
    status_source='none',
    statuses=(),
    fields=(
        f('entry_date', 'Date', 'date', column='entry_date', required=True),
        f('topic', 'Topic', 'text', required=True),
        f('reported_by', 'Conducted by', 'person', column='reported_by_id',
          required=True),
        f('department', 'Department', 'choice', column='department_id',
          choices_kind='department'),
        f('attendees', 'Attendees', 'number', required=True),
        f('location', 'Location', 'choice', column='location_id',
          choices_kind='location'),
        f('notes', 'Notes', 'textarea'),
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
        f('notes', 'Notes', 'textarea'),
    ),
)


HSE_REGISTERS = (
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
    """Registers behind one rail entry, in tab-strip order."""
    return tuple(r for r in HSE_REGISTERS if r.group == group)


def jsonb_fields(reg):
    """Fields that land in HseEntry.data rather than a column."""
    return tuple(fl for fl in reg.fields if fl.column is None)


def schedulable_registers():
    """The registers a recurring schedule may point at, in rail order."""
    return tuple(r for r in HSE_REGISTERS if r.schedulable)


def asset_field(reg):
    """The register's asset field, or None. A schedule is due once per
    asset when there is one, and once overall when there is not."""
    for fl in reg.fields:
        if fl.type == 'asset':
            return fl
    return None
