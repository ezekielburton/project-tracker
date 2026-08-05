"""
Throwaway helper to manually push a submission into a given review state,
purely for visually testing chunk 1's badge/locked rendering — bypasses
the real routes since none of them are wired to a UI button yet.
Edit PROJECT_ID / scope / STATE below, run, refresh the overlay in browser.
Delete this file once sub-step 6c is fully wired end to end.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app, db
from app.models import ProjectSubmission

app = create_app()

PROJECT_ID = 39          # change to whatever project you're testing
SCOPE = 'ckv'            # 'ckv' for Standard Brief / C&CM Concept & KV; for a
                          # customer scope you'd filter on posm_customer_id instead

# One of: 'draft', 'internal_review', 'internal_review_being_edited', 'internal_revision'
STATE = 'draft'

with app.app_context():
    sub = ProjectSubmission.query.filter_by( 
        project_id=PROJECT_ID, phase='concept_kv', posm_country=None,
        posm_customer_id=None, is_active=True,
    ).filter(ProjectSubmission.workflow_status.isnot(None)).first()

    assert sub is not None, "No active submission found for this scope — upload a file via the overlay first."

    if STATE == 'internal_review_being_edited':
        sub.workflow_status = 'internal_review'
        sub.is_being_edited = True
    elif STATE == 'draft':
        sub.workflow_status = 'draft'
        sub.is_being_edited = False
    else:
        sub.workflow_status = STATE
        sub.is_being_edited = False

    db.session.commit()
    print(f"Submission {sub.id} now: workflow_status={sub.workflow_status}, is_being_edited={sub.is_being_edited}")