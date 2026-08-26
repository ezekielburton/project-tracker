"""
One-off DATA fix, NOT a schema migration — do not run through migrate.py
(underscore prefix keeps it out of the auto-runner). Run directly: python3
migrations/_backfill_revision_counts.py

project.revision_count / deliverable.revision_count (both plain Integer
columns, default 0) are driven entirely by the NEW Submissions flow's
revision-confirm action (see project_overlay.py) — added with the M-series
redesign, so any project/deliverable that already had revision history
from BEFORE the redesign reads 0 there today, even though the old
free-text revision-request flow (ProjectRevision / ProjectRevisionDeliverable
— see app/models.py; still a live table, just unread by any current UI)
has the real history sitting right there.

This counts each legacy ProjectRevision row as one revision against its
project, and each ProjectRevisionDeliverable junction row as one revision
against that deliverable — same "one request = one revision" granularity
the new flow uses.

Guarded to only fill in rows still at revision_count == 0 — i.e. it ADDS
the legacy count for anything that has never logged a revision under the
new system, but does NOT add legacy history on top of an already-nonzero
count. That's a deliberate undercount for the rare project that's old
enough to have legacy ProjectRevision rows AND has already picked up a
real revision since the redesign — safer to leave that one short than to
risk this being re-run (or any future backfill) and double-adding on top
of a number that already includes some of the same history. Re-running
this script is therefore safe: the second run touches nothing, since every
row it could still act on is already at 0 after the first pass, or has a
real post-redesign count it correctly leaves alone.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project, Deliverable, ProjectRevision, ProjectRevisionDeliverable

app = create_app()

with app.app_context():
    project_counts = dict(
        db.session.query(ProjectRevision.project_id, db.func.count(ProjectRevision.id))
        .group_by(ProjectRevision.project_id)
        .all()
    )
    deliverable_counts = dict(
        db.session.query(ProjectRevisionDeliverable.deliverable_id, db.func.count(ProjectRevisionDeliverable.id))
        .group_by(ProjectRevisionDeliverable.deliverable_id)
        .all()
    )

    updated_projects = 0
    if project_counts:
        for project in Project.query.filter(
            Project.id.in_(project_counts.keys()), Project.revision_count == 0
        ).all():
            project.revision_count = project_counts[project.id]
            updated_projects += 1

    updated_deliverables = 0
    if deliverable_counts:
        for deliverable in Deliverable.query.filter(
            Deliverable.id.in_(deliverable_counts.keys()), Deliverable.revision_count == 0
        ).all():
            deliverable.revision_count = deliverable_counts[deliverable.id]
            updated_deliverables += 1

    db.session.commit()
    print(f"Legacy revision rows found for {len(project_counts)} project(s), {len(deliverable_counts)} deliverable(s).")
    print(f"Backfilled revision_count on {updated_projects} project(s) and {updated_deliverables} deliverable(s) "
          f"that were still at 0.")
