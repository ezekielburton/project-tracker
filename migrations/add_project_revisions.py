import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app import create_app, db

app = create_app()
with app.app_context():
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS project_revisions (
            id          SERIAL PRIMARY KEY,
            project_id  INTEGER NOT NULL
                            REFERENCES projects(id) ON DELETE CASCADE,
            message     TEXT NOT NULL,
            sent_by_id  INTEGER NOT NULL
                            REFERENCES users(id),
            sent_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS project_revision_deliverables (
            id             SERIAL PRIMARY KEY,
            revision_id    INTEGER NOT NULL
                               REFERENCES project_revisions(id) ON DELETE CASCADE,
            deliverable_id INTEGER NOT NULL
                               REFERENCES deliverables(id) ON DELETE CASCADE
        );
    """))
    db.session.commit()
    print("Done — project_revisions and project_revision_deliverables tables created.")
