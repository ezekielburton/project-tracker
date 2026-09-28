"""
The Lists & people page: the editable reference data behind the dropdowns.

One index of every list (basics, assets, choice lists) and one list open
at a time, addressed by its key: a reference kind, an asset kind, or
'people'. Severity and statuses are closed sets in code, not lists here.
"""

from sqlalchemy import func

from app.modules.core.shared.extensions import db
from app.modules.hse.lib.registers import HSE_REGISTERS
from app.modules.hse.models import (
    ASSET_KINDS, REFERENCE_KINDS, HseAsset, HsePerson, HseReference,
)


# Listed with People under Basics; every other reference kind is a choice list.
BASIC_KINDS = ('location', 'department')

PEOPLE = 'people'

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

# Asset kinds that carry a serial number.
SERIAL_ASSET_KINDS = ('machine',)

ASSET_KIND_LABELS = {
    'vehicle': 'Vehicles',
    'machine': 'Machines',
    'forklift': 'Forklifts',
    'area': 'Areas',
}

# What an asset's ref holds, per kind.
REF_LABELS = {
    'vehicle': 'Plate',
    'forklift': 'Plate / serial',
    'machine': 'Asset tag',
}


def kind_label(kind):
    return KIND_LABELS.get(kind, kind.replace('_', ' ').capitalize())


def list_label(key):
    if key == PEOPLE:
        return 'People'
    if key in ASSET_KINDS:
        return ASSET_KIND_LABELS.get(key, key.title())
    return kind_label(key)


def choice_kinds():
    """Reference kinds shown as choice lists, A–Z by label."""
    return tuple(sorted((k for k in REFERENCE_KINDS if k not in BASIC_KINDS),
                        key=kind_label))


def list_keys():
    """Every list the page can open, in index order."""
    return BASIC_KINDS + (PEOPLE,) + ASSET_KINDS + choice_kinds()


def used_in(kind):
    """Labels of the registers with a choice field filled from this
    reference kind, in declaration order."""
    return [r.label for r in HSE_REGISTERS
            if any(f.type == 'choice' and f.choices_kind == kind for f in r.fields)]


def serialize_reference(row):
    return {'id': row.id, 'label': row.label, 'active': row.active}


def serialize_person(row):
    return {
        'id': row.id, 'label': row.name, 'role': row.role,
        'organisation': row.organisation, 'is_external': row.is_external,
        'can_hold_actions': row.can_hold_actions, 'email': row.email,
        'phone': row.phone, 'active': row.active,
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


def asset_rows(kind):
    return (HseAsset.query.filter_by(kind=kind)
            .order_by(HseAsset.active.desc(), HseAsset.label).all())


def index():
    """The index: Basics, Assets and Choice lists, each list with how many
    of its values are in use. People and assets can't be quick-added from a
    form, so an empty one is flagged."""
    refs = dict(db.session.query(HseReference.kind, func.count(HseReference.id))
                .filter(HseReference.active.is_(True))
                .group_by(HseReference.kind).all())
    assets = dict(db.session.query(HseAsset.kind, func.count(HseAsset.id))
                  .filter(HseAsset.active.is_(True))
                  .group_by(HseAsset.kind).all())
    people = HsePerson.query.filter_by(active=True).count()

    def item(key, count, must_fill=False):
        return {'key': key, 'label': list_label(key), 'count': count,
                'empty': must_fill and not count}

    return [
        {'label': 'Basics',
         'items': [item(k, refs.get(k, 0)) for k in BASIC_KINDS]
                  + [item(PEOPLE, people, must_fill=True)]},
        {'label': 'Assets',
         'items': [item(k, assets.get(k, 0), must_fill=True) for k in ASSET_KINDS]},
        {'label': 'Choice lists',
         'items': [item(k, refs.get(k, 0)) for k in choice_kinds()]},
    ]


def list_view(key):
    """One list: rows in use and retired rows kept apart, plus what the page
    needs to label it. `key` must come from list_keys()."""
    if key == PEOPLE:
        rows = [serialize_person(r) for r in people_rows()]
        view = {'kind': PEOPLE}
    elif key in ASSET_KINDS:
        rows = [serialize_asset(r) for r in asset_rows(key)]
        view = {'kind': 'asset', 'has_serial': key in SERIAL_ASSET_KINDS,
                'ref_label': REF_LABELS.get(key, 'Code')}
    else:
        rows = [serialize_reference(r) for r in reference_rows(key)]
        view = {'kind': 'reference', 'used_in': used_in(key)}
    view.update(key=key, label=list_label(key),
                rows=[r for r in rows if r['active']],
                retired=[r for r in rows if not r['active']])
    return view


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
