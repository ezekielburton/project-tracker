"""
One-off DATA fix, NOT a schema migration — do not run through migrate.py
(underscore prefix keeps it out of the auto-runner). Run directly: python3
migrations/_backfill_preproduction_needs.py

Catches up two backlogs in one pass: (1) any deliverable approved before
derive_preproduction_needs existed at all, and (2) any deliverable approved
under the old 2-stream scheme (needs_artwork=True) that now needs its 2D/3D
split figured out. Safe to run more than once — only touches rows where
needs_2d/needs_3d/needs_technical are all still False, so it never
overwrites a real decision made after this point.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.models import Deliverable
from app.status_vocabulary import derive_preproduction_needs

app = create_app()

with app.app_context():
    stuck = Deliverable.query.filter_by(
        status='approved', needs_2d=False, needs_3d=False, needs_technical=False
    ).all()

    updated = 0
    for d in stuck:
        needs_2d, needs_3d, needs_technical = derive_preproduction_needs(d)
        if needs_2d or needs_3d or needs_technical:
            d.needs_2d = needs_2d
            d.needs_3d = needs_3d
            d.needs_technical = needs_technical
            updated += 1

    db.session.commit()
    print(f"Checked {len(stuck)} already-approved deliverables, updated {updated}.")