"""
Fills the HSE reference lists and the real fleet, so the officer opens a
working form instead of twenty empty dropdowns.

    python seed_hse_lists.py

Idempotent: a value already present is left exactly as it is, including a
deactivated one — reviving something he retired on purpose would be worse
than missing it. Nothing here is demo data; it is his to rename, extend or
switch off on the Lists & people page.

Where the workbook carried a real dropdown, these are its values verbatim.
Where it only had a sample row or two, the obvious neighbours are added and
marked below — those are the ones to check with him first.
"""
import sys

from app import create_app
from app.modules.core.shared.extensions import db
from app.modules.hse.models import HseAsset, HseReference


# --- reference lists ------------------------------------------------------
# (*) = extended past what the workbook actually contained.

REFERENCE_LISTS = {
    'location': ['Factory 1', 'Factory 2', 'Warehouse A', 'Warehouse B', 'Office HQ'],
    'department': ['Manufacturing', 'Logistics', 'Maintenance', 'Admin',
                   'Security', 'HSE', 'Operations'],
    'incident_type': ['Slip/Fall', 'Electrical', 'Equipment Failure', 'Chemical',
                      'Fire Hazard', 'Other'],
    # (*) the workbook had free text here, not a list
    'issue_type': ['Housekeeping', 'Fire safety', 'Electrical', 'Chemical storage',
                   'PPE', 'Machine guarding', 'Working at height', 'Other'],
    'compliance_type': ['Certificate', 'Permit', 'Licence', 'Insurance', 'Policy'],
    # (*) one sample row only
    'injury_type': ['Cut / laceration', 'Burn', 'Bruise / contusion',
                    'Sprain / strain', 'Eye injury', 'Fracture',
                    'Chemical exposure', 'Other'],
    # (*) two sample rows only
    'body_part': ['Head', 'Eye', 'Face', 'Neck', 'Shoulder', 'Arm', 'Hand',
                  'Finger', 'Back', 'Leg', 'Knee', 'Foot', 'Other'],
    # (*) two sample rows only
    'ppe_type': ['Hard Hat', 'Safety Boots', 'Safety Glasses', 'Gloves',
                 'Hi-Vis Vest', 'Ear Protection', 'Respirator / Mask', 'Harness'],
    # (*) two sample rows only
    'inspection_type': ['Pre-Trip Check', 'Weekly Check', 'Monthly Check',
                        'Post-Incident Check'],
    # (*) one sample row only
    'service_type': ['Full Service', 'Oil Change', 'Tyre Replacement',
                     'Brake Service', 'Repair'],
    'vehicle_document': ['Registration', 'Insurance'],
    'maintenance_type': ['Preventive', 'Corrective', 'Emergency'],
    'pm_frequency': ['Weekly', 'Monthly', 'Quarterly', 'Annually', 'Emergency'],
    # (*) one sample row only
    'tool_category': ['Power Tool', 'Hand Tool', 'Lifting Equipment',
                      'Measuring', 'Access Equipment'],
    'condition': ['Good', 'Fair', 'Poor', 'Condemned'],
    # (*) two sample rows only
    'material_category': ['PPE', 'First Aid', 'Signage', 'Cleaning',
                          'Spill Control', 'Other'],
    # (*) two sample rows only
    'unit': ['Each', 'Box', 'Pack', 'Kit', 'Litre', 'Roll'],
    # (*) two sample rows only
    'training_type': ['Induction', 'Toolbox Talk', 'Refresher', 'Certification',
                      'External Course'],
    'expense_category': ['Third-Party Training', 'Training Materials',
                         'Refreshments', 'Training-Related Purchases', 'Other'],
}


# --- assets ---------------------------------------------------------------
# The six vehicles are the real fleet off the Mileage Tracker's dropdown —
# plate as the ref, so every register points at one record rather than four
# spellings of the same truck.

ASSETS = [
    ('vehicle', 'Hino C17131', 'C17131'),
    ('vehicle', 'Hino L61056', 'L61056'),
    ('vehicle', 'Hino C79735', 'C79735'),
    ('vehicle', 'Ford Ranger N64812', 'N64812'),
    ('vehicle', 'Mitsubishi L200 L47131', 'L47131'),
    # The workbook says "please confirm make/model" — left as it stands so
    # the gap is visible rather than invented.
    ('vehicle', 'Vehicle 6 (confirm make/model)', 'T28206'),
    ('machine', 'CNC Lathe 1', 'M-01'),
    ('machine', 'Table Saw', 'M-02'),
    ('machine', 'Compressor A', 'M-03'),
    ('forklift', 'Forklift 1', 'FL-01'),
]


def seed_references():
    added = 0
    for kind, labels in REFERENCE_LISTS.items():
        existing = {r.label for r in HseReference.query.filter_by(kind=kind).all()}
        for order, label in enumerate(labels):
            if label in existing:
                continue
            db.session.add(HseReference(kind=kind, label=label,
                                        sort_order=order, active=True))
            added += 1
    return added


def seed_assets():
    added = 0
    for kind, label, ref in ASSETS:
        # Matched on ref, not label: a plate is the identity, a name is not.
        if HseAsset.query.filter_by(ref=ref).first():
            continue
        db.session.add(HseAsset(kind=kind, label=label, ref=ref, active=True))
        added += 1
    return added


def main():
    app = create_app()
    with app.app_context():
        refs = seed_references()
        assets = seed_assets()
        db.session.commit()
        print(f'Done — {refs} list values and {assets} assets added.')
        if not refs and not assets:
            print('(everything was already there)')


if __name__ == '__main__':
    sys.exit(main())
