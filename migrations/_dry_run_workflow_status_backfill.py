"""
DRY RUN ONLY — prints what backfill_submission_workflow_status.py would do,
without writing anything. Not a tracked migration (leading underscore is
skipped by migrate.py's get_all_scripts()). Run directly:
    python migrations/_dry_run_workflow_status_backfill.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from app.models import ProjectSubmission, Project, ProjectPosmChannel

app = create_app()

with app.app_context():
    submissions = ProjectSubmission.query.order_by(ProjectSubmission.id).all()
    counts = {'draft': 0, 'revision_requested': 0, 'approved': 0, 'sent_to_client': 0}
    rows_to_print = []

    for sub in submissions:
        if sub.submitted_to_client_at is None:
            new_status = 'draft'
            parent_note = '—'
        elif sub.is_flagged:
            new_status = 'revision_requested'
            parent_note = '—'
        else:
            if sub.posm_country:
                channel = ProjectPosmChannel.query.filter_by(
                    project_id=sub.project_id,
                    posm_country=sub.posm_country,
                    posm_customer_id=sub.posm_customer_id
                ).first()
                parent_approved = bool(channel and channel.status == 'approved')
                parent_note = f"channel={channel.status if channel else 'NOT FOUND'}"
            else:
                project = Project.query.get(sub.project_id)
                parent_approved = bool(project and project.project_status == 'approved')
                parent_note = f"project={project.project_status if project else 'NOT FOUND'}"

            new_status = 'approved' if parent_approved else 'sent_to_client'

        counts[new_status] += 1
        rows_to_print.append(
            f"  sub#{sub.id:<5} project={sub.project_id:<5} "
            f"posm_country={str(sub.posm_country):<8} posm_customer_id={str(sub.posm_customer_id):<5} "
            f"submitted={'Y' if sub.submitted_to_client_at else 'N'} flagged={sub.is_flagged} "
            f"{parent_note:<25} -> {new_status}"
        )

    print(f"Total submissions: {len(submissions)}")
    print(f"  draft={counts['draft']}  sent_to_client={counts['sent_to_client']}  "
          f"revision_requested={counts['revision_requested']}  approved={counts['approved']}")
    print()
    print("Per-row detail (all rows):")
    for line in rows_to_print:
        print(line)

    not_found = [r for r in rows_to_print if 'NOT FOUND' in r]
    if not_found:
        print(f"\n⚠ {len(not_found)} row(s) had no matching parent record — these fell back to 'sent_to_client'. Review them:")
        for line in not_found:
            print(line)