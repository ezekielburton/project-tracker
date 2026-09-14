"""
Seeds the HSE module with a demo week so the register surface can be seen
with rows in it. Dubai locale: AED, UAE plates.

    python seed_hse_demo.py            # add the demo data
    python seed_hse_demo.py --wipe     # remove only the demo entries

Entries carry a `_demo` marker in their JSONB, and --wipe removes exactly
those. The reference lists, assets and people it creates are left alone:
they are the officer's own data to keep and edit, not demo clutter.
"""
import random
import sys
from datetime import date, timedelta

from app import create_app
from app.modules.core.shared.extensions import db
from app.modules.hse.lib.refs import next_ref
from app.modules.hse.models import HseAsset, HseEntry, HsePerson, HseReference

DEMO_KEY = '_demo'

LOCATIONS = ['Factory 1', 'Factory 2', 'Warehouse A', 'Warehouse B', 'Yard']
DEPARTMENTS = ['Manufacturing', 'Logistics', 'Maintenance', 'Admin', 'HSE']
INCIDENT_TYPES = ['Slip/Fall', 'Electrical', 'Equipment failure', 'Chemical',
                  'Manual handling', 'Near miss']
ISSUE_TYPES = ['Unlabeled chemical container', 'Blocked fire exit', 'Damaged PPE',
               'Missing machine guard', 'Housekeeping']
COMPLIANCE_TYPES = ['Certificate', 'Permit', 'Licence', 'Insurance']

PEOPLE = [
    ('M. Haddad', 'HSE Officer', 'Vitamin', False, False),
    ('S. Pillai', 'Warehouse Supervisor', 'Vitamin', False, False),
    ('T. Nair', 'Maintenance Lead', 'Vitamin', False, False),
    ('R. Costa', 'Safety Supervisor', 'Vitamin', False, False),
    ('A. Rahman', 'Production Manager', 'Vitamin', False, True),
    ('K. Mathews', 'General Manager', 'Vitamin', False, True),
    ('J. Fernandes', 'Fleet Contractor', 'Al Wasl Motors', True, True),
]

ASSETS = [
    ('vehicle', 'GMC Sierra', 'D-55831'),
    ('vehicle', 'Toyota Hilux', 'D-41207'),
    ('vehicle', 'Nissan Urvan', 'A-77104'),
    ('forklift', 'Forklift FL-01', 'FL-01'),
    ('forklift', 'Forklift FL-02', 'FL-02'),
    ('machine', 'CNC Lathe 1', 'CNC-01'),
    ('machine', 'Hydraulic Press 2', 'PRS-02'),
]

COMPLIANCE_ITEMS = [
    ('ISO 45001 Certification', 'Certificate', -470, -105),
    ('Fire Department Clearance', 'Permit', -317, 48),
    ('Trade Licence', 'Licence', -300, 65),
    ('Public Liability Insurance', 'Insurance', -350, 15),
    ('Chemical Storage Permit', 'Permit', -200, 165),
    ('Lifting Equipment Certificate', 'Certificate', -280, -12),
]


def _ref_rows():
    """Create the option lists, skipping any label already there."""
    wanted = ([('location', v) for v in LOCATIONS]
              + [('department', v) for v in DEPARTMENTS]
              + [('incident_type', v) for v in INCIDENT_TYPES]
              + [('issue_type', v) for v in ISSUE_TYPES]
              + [('compliance_type', v) for v in COMPLIANCE_TYPES])
    existing = {(r.kind, r.label) for r in HseReference.query.all()}
    made = {}
    for order, (kind, label) in enumerate(wanted):
        if (kind, label) not in existing:
            db.session.add(HseReference(kind=kind, label=label, sort_order=order))
    db.session.flush()
    for r in HseReference.query.all():
        made.setdefault(r.kind, []).append(r)
    return made


def _people():
    have = {p.name for p in HsePerson.query.all()}
    for name, role, org, external, holds in PEOPLE:
        if name not in have:
            db.session.add(HsePerson(name=name, role=role, organisation=org,
                                     is_external=external, can_hold_actions=holds))
    db.session.flush()
    return HsePerson.query.all()


def _assets():
    have = {a.ref for a in HseAsset.query.all()}
    for kind, label, ref in ASSETS:
        if ref not in have:
            db.session.add(HseAsset(kind=kind, label=label, ref=ref))
    db.session.flush()
    return HseAsset.query.all()


def seed():
    rng = random.Random(20260914)
    today = date.today()
    refs = _ref_rows()
    people = _people()
    _assets()

    locations = refs['location']
    departments = refs['department']

    # Incidents — 30, matching the workbook's all-time total, with 13 still
    # open across Open / In Progress / Escalated.
    statuses = ['Resolved'] * 17 + ['Open'] * 2 + ['In Progress'] * 5 + ['Escalated'] * 6
    rng.shuffle(statuses)
    for status in statuses:
        started = today - timedelta(days=rng.randint(3, 300))
        closed = None
        if status == 'Resolved':
            closed = started + timedelta(days=rng.randint(1, 45))
            if closed > today:
                closed = today
        db.session.add(HseEntry(
            register='incidents', ref=next_ref('incidents'),
            entry_date=started, status=status, closed_at=closed,
            severity=rng.choice(['Low', 'Medium', 'High', 'Critical']),
            location_id=rng.choice(locations).id,
            department_id=rng.choice(departments).id,
            reported_by_id=rng.choice(people).id,
            assigned_to_id=rng.choice(people).id,
            data={DEMO_KEY: True,
                  'incident_type': rng.choice(INCIDENT_TYPES),
                  'description': 'See incident report file.'},
        ))

    # General inspections — a run of weekly checks, a few still open.
    for week in range(12):
        started = today - timedelta(days=7 * week + rng.randint(0, 2))
        open_one = week in (0, 3, 7)
        db.session.add(HseEntry(
            register='general_inspection', ref=next_ref('general_inspection'),
            entry_date=started,
            status='Open' if open_one else 'Closed',
            closed_at=None if open_one else started + timedelta(days=rng.randint(1, 6)),
            severity=rng.choice(['Low', 'Medium', 'High']),
            location_id=rng.choice(locations).id,
            reported_by_id=rng.choice(people).id,
            assigned_to_id=rng.choice(people).id,
            data={DEMO_KEY: True, 'issue_type': rng.choice(ISSUE_TYPES)},
        ))

    # Compliance & renewal — status is computed from the expiry date, so
    # nothing writes it here. Two are already past their date.
    for label, kind, issued_offset, expiry_offset in COMPLIANCE_ITEMS:
        db.session.add(HseEntry(
            register='compliance_renewal', ref=next_ref('compliance_renewal'),
            entry_date=today + timedelta(days=issued_offset),
            due_at=today + timedelta(days=expiry_offset),
            assigned_to_id=rng.choice(people).id,
            data={DEMO_KEY: True, 'item': label, 'compliance_type': kind},
        ))

    db.session.commit()
    print(f'Seeded {HseEntry.query.count()} HSE entries, '
          f'{HsePerson.query.count()} people, {HseAsset.query.count()} assets.')


def wipe():
    """Removes only the entries this script created. The reference lists,
    people and assets stay — they are real data the officer would edit."""
    demo = HseEntry.query.filter(HseEntry.data[DEMO_KEY].astext == 'true').all()
    for entry in demo:
        db.session.delete(entry)
    db.session.commit()
    print(f'Removed {len(demo)} demo entries. Lists, people and assets left in place.')


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        if '--wipe' in sys.argv:
            wipe()
        else:
            seed()
