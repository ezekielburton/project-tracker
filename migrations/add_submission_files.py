import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app import create_app, db

app = create_app()
with app.app_context():
    # Supplementary files attached to a ProjectSubmission.
    # Multiple extra files can belong to one submission; they are stored on NAS
    # in the project's Submissions/ folder alongside the primary deck.
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS project_submission_files (
            id SERIAL PRIMARY KEY,
            submission_id INTEGER NOT NULL
                REFERENCES project_submissions(id) ON DELETE CASCADE,
            project_id INTEGER NOT NULL
                REFERENCES projects(id) ON DELETE CASCADE,
            original_filename VARCHAR(255) NOT NULL,
            file_type VARCHAR(10) NOT NULL,
            uploaded_by_id INTEGER NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            uploaded_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """))
    db.session.commit()
    print("Done — project_submission_files table created.")
