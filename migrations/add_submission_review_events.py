"""
Migration: add Submissions internal-review event log + edit-in-progress
marker (M3 Step 4 sub-step 6).

project_submission_events (new table): append-only history for one
submission's internal-review cycle — a designer's optional note on Submit
for Review, a designer's required reason on Edit, or CS's required (rich-
text, may include inline images) message on Flag Internal Revision. See
the ProjectSubmissionEvent model docstring for the full reasoning.

is_being_edited / editing_started_at (project_submissions): set while a
designer is mid-fix after clicking Edit on an already-locked submission —
a modifier on top of workflow_status='internal_review', not a new phase.
Cleared when the designer re-submits for review. The later SSE work (M4)
will watch this to show CS a live "currently being edited" marker.

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
            CREATE TABLE IF NOT EXISTS project_submission_events (
                id SERIAL PRIMARY KEY,
                submission_id INTEGER NOT NULL REFERENCES project_submissions(id),
                event_type VARCHAR(30) NOT NULL,
                author_id INTEGER NOT NULL REFERENCES users(id),
                message TEXT,
                created_at TIMESTAMP
            );
        """))
        conn.execute(text("""
            ALTER TABLE project_submissions
            ADD COLUMN IF NOT EXISTS is_being_edited BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.execute(text("""
            ALTER TABLE project_submissions
            ADD COLUMN IF NOT EXISTS editing_started_at TIMESTAMP;
        """))
        conn.commit()

    print("Migration complete: project_submission_events table created; "
          "is_being_edited, editing_started_at added to project_submissions.")