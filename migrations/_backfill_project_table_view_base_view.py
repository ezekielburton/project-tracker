"""
One-off DATA fix, NOT a schema migration — do not run through migrate.py
(underscore prefix keeps it out of the auto-runner). Run directly: python3
migrations/_backfill_project_table_view_base_view.py

The Projects list "Approved" fixed tab was renamed to "Design Complete" and
its view key from 'approved' to 'design_complete' (18 Aug 2026, per Ezekiel
— the raw project_status 'approved' is a transient in-flight status now,
and keeping the view key named 'approved' next to that was confusing).
Anyone who had already saved a custom view layered on top of the old
'approved' preset has that choice stored in ProjectTableView.base_view —
this updates those rows so the saved view keeps working under the new key
instead of silently falling back to 'my' (see _base_query_for_view()'s
`saved_view.base_view if saved_view else 'my'` — an unrecognized base_view
value isn't rejected there, it just falls through to the 'my' branch,
which would silently change what the saved view shows rather than error).
Safe to run more than once — only touches rows still on the old value.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import ProjectTableView

app = create_app()

with app.app_context():
    stale = ProjectTableView.query.filter_by(base_view='approved').all()

    for v in stale:
        v.base_view = 'design_complete'

    db.session.commit()
    print(f"Updated {len(stale)} saved view(s) from base_view='approved' to 'design_complete'.")
