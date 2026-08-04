from app import create_app, db
from app.models import ProjectPosmChannel, ProjectSubmission, ProjectRevision, ProjectCustomer, Project

app = create_app()

# Confirmed via diagnose_gulf_submissions.py: these are the only Gulf regions where
# every historical submission touches exactly one customer. Oman is deliberately
# excluded — its submissions cover multiple customers in one combined deck and
# can't be split; they stay as frozen, read-only legacy history.
MIGRATIONS = [
    {'project_id': 54, 'region': 'kuwait', 'customer_id': 28},
    {'project_id': 54, 'region': 'bahrain', 'customer_id': 29},
]

with app.app_context():
    print("Preview of changes (nothing written yet):\n")
    plan = []
    for m in MIGRATIONS:
        project_id, region, customer_id = m['project_id'], m['region'], m['customer_id']

        customer = ProjectCustomer.query.get(customer_id)
        if not customer or customer.project_id != project_id:
            print(f"SKIP {region} on project {project_id} — customer {customer_id} not found / wrong project")
            continue

        channel = ProjectPosmChannel.query.filter_by(
            project_id=project_id, posm_country=region, posm_customer_id=None
        ).first()
        subs = ProjectSubmission.query.filter_by(
            project_id=project_id, posm_country=region, posm_customer_id=None
        ).all()
        revs = ProjectRevision.query.filter_by(
            project_id=project_id, posm_country=region, posm_customer_id=None
        ).all()
        project = Project.query.get(project_id)
        region_count = (project.posm_country_revision_counts or {}).get(region, 0)

        print(f"{region} on project {project_id} ({project.name}) -> customer {customer_id} ({customer.customer.name}):")
        print(f"  channel: {'#' + str(channel.id) if channel else 'NONE FOUND'}")
        print(f"  submissions to update: {[s.id for s in subs]}")
        print(f"  revisions to update: {[r.id for r in revs]}")
        print(f"  revision count to carry over: {region_count}")
        print()
        plan.append((channel, subs, revs, customer, region_count))

    confirm = input("Type 'yes' to apply these changes: ")
    if confirm.strip().lower() != 'yes':
        print("Aborted — no changes made.")
    else:
        for channel, subs, revs, customer, region_count in plan:
            if channel:
                channel.posm_customer_id = customer.id
            for s in subs:
                s.posm_customer_id = customer.id
            for r in revs:
                r.posm_customer_id = customer.id
            if region_count:
                customer.posm_revision_count = (customer.posm_revision_count or 0) + region_count
        db.session.commit()
        print("Done — changes committed.")