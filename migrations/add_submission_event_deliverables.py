"""
Migration: add project_submission_event_deliverables (M3 Step 4 sub-step 8 —
Client Approval batch notes).

Records which deliverables were part of a given ProjectSubmissionEvent —
specifically the new 'client_approval' event_type written when CS clicks
Mark Approved on a partial batch of deliverables, with a free-text note
(stored on ProjectSubmissionEvent.message, already a nullable Text column,
so no change needed there) about that batch for the future Pre-Production
tab to display. Same junction-table shape as ProjectSubmissionDeliverable,
just pointed at events instead of the submission itself, so a submission
that gets approved in several separate batches over time keeps a distinct
note + deliverable list per batch instead of one note being overwritten.

Run via migrate.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_submission_event_deliverables (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES project_submission_events(id),
                deliverable_id INTEGER NOT NULL REFERENCES deliverables(id)
            );
        """))
        conn.commit()

    print("Migration complete: project_submission_event_deliverables table created.")
