"""
Migration: add workflow_status + supporting fields to project_submissions.
workflow_status is the explicit lifecycle column (draft / sent_to_client /
revision_requested / approved) backing the new Submissions flow — added
here as a nullable column; the one-time backfill from existing signals
(submitted_to_client_at, is_flagged, parent approval) is a separate,
carefully-verified follow-up script, not part of this file.
last_internal_review_notified_at: modified-since check for the "Inform CS
  for Internal Review" ping.
cs_note: optional CS note on a submission.
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
            ALTER TABLE project_submissions
            ADD COLUMN IF NOT EXISTS workflow_status VARCHAR(30);
        """))
        conn.execute(text("""
            ALTER TABLE project_submissions
            ADD COLUMN IF NOT EXISTS last_internal_review_notified_at TIMESTAMP;
        """))
        conn.execute(text("""
            ALTER TABLE project_submissions
            ADD COLUMN IF NOT EXISTS cs_note TEXT;
        """))
        conn.commit()

    print("Migration complete: workflow_status, last_internal_review_notified_at, cs_note added to project_submissions.")