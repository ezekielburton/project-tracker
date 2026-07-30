import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app import create_app, db

app = create_app()
with app.app_context():
    # Junction table that links a submission to the deliverables included in it.
    # ON DELETE CASCADE on both FKs so rows are cleaned up automatically
    # if either the submission or the deliverable is deleted.
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS project_submission_deliverables (
            id SERIAL PRIMARY KEY,
            submission_id INTEGER NOT NULL
                REFERENCES project_submissions(id) ON DELETE CASCADE,
            deliverable_id INTEGER NOT NULL
                REFERENCES deliverables(id) ON DELETE CASCADE
        );
    """))
    db.session.commit()
    print("Done — project_submission_deliverables table created.")
