"""
One-off DATA fix, NOT a schema migration — do not run through migrate.py
(underscore prefix keeps it out of the auto-runner, same convention as
_dry_run_workflow_status_backfill.py). Run directly: python3 migrations/
_backfill_preproduction_needs.py

Why this exists (13 Aug 2026): needs_technical/needs_artwork are now
auto-set the moment a deliverable reaches 'approved' (see
status_vocabulary.derive_preproduction_needs, called from both the
Client Approval route and Skip to Pre-Production). But any deliverable
that was ALREADY approved before that code existed never got flagged —
it's stuck reading "Client Approved" forever and will never appear on
the Pre-Production tab, because nothing ever set those two columns for
it. This is a one-time catch-up for exactly that backlog: every already-
approved deliverable, run through the same derivation the live routes
now use automatically going forward.

Safe to run more than once — it only touches rows currently sitting at
needs_technical=False AND needs_artwork=False, so it will never overwrite
a real per-deliverable decision made after this point.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.models import Deliverable
from app.status_vocabulary import derive_preproduction_needs

app = create_app()

with app.app_context():
    stuck = Deliverable.query.filter_by(
        status='approved', needs_technical=False, needs_artwork=False
    ).all()

    updated = 0
    for d in stuck:
        needs_technical, needs_artwork = derive_preproduction_needs(d)
        if needs_technical or needs_artwork:
            d.needs_technical = needs_technical
            d.needs_artwork = needs_artwork
            updated += 1

    db.session.commit()
    print(f"Checked {len(stuck)} already-approved deliverables, updated {updated}.")
