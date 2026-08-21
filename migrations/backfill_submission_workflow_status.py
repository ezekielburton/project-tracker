"""
Migration: backfill ProjectSubmission.workflow_status from existing signals.
One-time data migration — see Projects Redesign Architecture.md §C.
Logic verified against a dry run on a real DB restore (30 Jul 2026) via
migrations/_dry_run_workflow_status_backfill.py before this was run.

Rule (applied to every existing row):
  submitted_to_client_at IS NULL                                  -> 'draft'
  submitted_to_client_at IS NOT NULL AND is_flagged                -> 'revision_requested'
  submitted_to_client_at IS NOT NULL AND NOT is_flagged AND parent_approved     -> 'approved'
  submitted_to_client_at IS NOT NULL AND NOT is_flagged AND NOT parent_approved -> 'sent_to_client'

"Parent approved" depends on brief type:
  - Standard / concept_kv submissions (posm_country IS NULL): parent is the
    Project itself -> project.project_status == 'approved'.
  - POSM submissions (posm_country IS NOT NULL): parent is the matching
    ProjectPosmChannel (same project_id + posm_country + posm_customer_id) ->
    channel.status == 'approved'.

Old flag fields (is_flagged, submitted_to_client_at, etc.) are left exactly
as-is — this migration only sets the new workflow_status value alongside them.
Run via migrate.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.models import ProjectSubmission, Project, ProjectPosmChannel

app = create_app()

with app.app_context():
    submissions = ProjectSubmission.query.all()
    counts = {'draft': 0, 'revision_requested': 0, 'approved': 0, 'sent_to_client': 0}
    not_found = 0

    for sub in submissions:
        if sub.submitted_to_client_at is None:
            new_status = 'draft'
        elif sub.is_flagged:
            new_status = 'revision_requested'
        else:
            if sub.posm_country:
                channel = ProjectPosmChannel.query.filter_by(
                    project_id=sub.project_id,
                    posm_country=sub.posm_country,
                    posm_customer_id=sub.posm_customer_id
                ).first()
                if channel is None:
                    not_found += 1
                parent_approved = bool(channel and channel.status == 'approved')
            else:
                project = Project.query.get(sub.project_id)
                parent_approved = bool(project and project.project_status == 'approved')

            new_status = 'approved' if parent_approved else 'sent_to_client'

        sub.workflow_status = new_status
        counts[new_status] += 1

    db.session.commit()
    print(f"Migration complete: backfilled workflow_status on {len(submissions)} submissions.")
    print(f"  draft={counts['draft']}  sent_to_client={counts['sent_to_client']}  "
          f"revision_requested={counts['revision_requested']}  approved={counts['approved']}")
    if not_found:
        print(f"  ⚠ {not_found} row(s) had no matching POSM channel — fell back to sent_to_client.")