"""
The Lists & people page: the editable reference data behind the dropdowns.

Locations and Departments get their own tabs; every other reference kind
shares "Other lists", so a new kind needs no change here. Severity and
statuses are closed sets in code and are not editable here.
"""

from app.modules.hse.models import (
    ASSET_KINDS, REFERENCE_KINDS, HseAsset, HsePerson, HseReference,
)


# Reference kinds that earn their own tab. Everything else is grouped.
PROMINENT_KINDS = ('location', 'department')

# Display names for the kinds. Missing kinds fall back to a capitalised key.
KIND_LABELS = {
    'location': 'Locations',
    'department': 'Departments',
    'incident_type': 'Incident types',
    'issue_type': 'Issue types',
    'compliance_type': 'Compliance types',
    'injury_type': 'Injury types',
    'body_part': 'Body parts',
    'ppe_type': 'PPE types',
    'inspection_type': 'Inspection types',
    'service_type': 'Service types',
    'vehicle_document': 'Vehicle documents',
    'maintenance_type': 'Maintenance types',
    'pm_frequency': 'PM frequencies',
    'tool_category': 'Tool categories',
    'condition': 'Conditions',
    'material_category': 'Material categories',
    'unit': 'Units',
    'training_type': 'Training types',
    'expense_category': 'Expense categories',
    'compliance_item': 'Compliance items',
}

# Asset kinds that carry a serial number on this page.
SERIAL_ASSET_KINDS = ('machine',)

ASSET_KIND_LABELS = {
    'vehicle': 'Vehicles',
    'machine': 'Machines',
    'forklift': 'Forklifts',
    'area': 'Areas',
}


def kind_label(kind):
    return KIND_LABELS.get(kind, kind.replace('_', ' ').capitalize())


def other_kinds():
    """Reference kinds sharing the 'Other lists' tab."""
    return tuple(k for k in REFERENCE_KINDS if k not in PROMINENT_KINDS)


def tabs():
    """The tab strip, in order."""
    out = [{'key': k, 'label': kind_label(k)} for k in PROMINENT_KINDS]
    out.append({'key': 'people', 'label': 'People'})
    out.append({'key': 'assets', 'label': 'Assets'})
    out.append({'key': 'other', 'label': 'Other lists'})
    return out


def serialize_reference(row):
    return {'id': row.id, 'label': row.label, 'active': row.active}


def serialize_person(row):
    return {
        'id': row.id, 'label': row.name, 'role': row.role,
        'organisation': row.organisation, 'is_external': row.is_external,
        'can_hold_actions': row.can_hold_actions, 'active': row.active,
    }


def serialize_asset(row):
    return {'id': row.id, 'label': row.label, 'ref': row.ref,
            'serial_no': row.serial_no, 'kind': row.kind, 'active': row.active}


def reference_rows(kind):
    return (HseReference.query.filter_by(kind=kind)
            .order_by(HseReference.active.desc(), HseReference.sort_order,
                      HseReference.label).all())


def people_rows():
    return HsePerson.query.order_by(HsePerson.active.desc(), HsePerson.name).all()


def asset_rows():
    return HseAsset.query.order_by(HseAsset.active.desc(), HseAsset.kind,
                                   HseAsset.label).all()


def panel_for(tab_key):
    """What one tab shows: a list of sections, each with its own rows. Only
    'other' has more than one section."""
    if tab_key in PROMINENT_KINDS:
        return [{'kind': tab_key, 'label': kind_label(tab_key),
                 'rows': [serialize_reference(r) for r in reference_rows(tab_key)]}]
    if tab_key == 'people':
        return [{'kind': 'people', 'label': 'People',
                 'rows': [serialize_person(r) for r in people_rows()]}]
    if tab_key == 'assets':
        rows = [serialize_asset(r) for r in asset_rows()]
        return [{'kind': 'assets', 'label': ASSET_KIND_LABELS.get(k, k.title()),
                 'asset_kind': k, 'has_serial': k in SERIAL_ASSET_KINDS,
                 'rows': [r for r in rows if r['kind'] == k]}
                for k in ASSET_KINDS]
    return [{'kind': k, 'label': kind_label(k),
             'rows': [serialize_reference(r) for r in reference_rows(k)]}
            for k in other_kinds()]


def find_or_revive_reference(kind, label):
    """Quick-add: reuse an existing label, reactivating it if needed, so no
    duplicate is made. Returns (row, created); `created` is also True when
    a deactivated row is revived."""
    existing = HseReference.query.filter_by(kind=kind, label=label).first()
    if existing:
        revived = not existing.active
        existing.active = True
        return existing, revived
    return HseReference(kind=kind, label=label, active=True), True
