"""
Migration: create project_notes table.
The outlier-documentation escape hatch (Projects Redesign Architecture.md
§11) — freeform, attributed, timestamped notes with an optional file link
and tags, distinct from the machine-written activity log.
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
            CREATE TABLE IF NOT EXISTS project_notes (
                id         SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                author_id  INTEGER NOT NULL REFERENCES users(id),
                body       TEXT NOT NULL,
                file_link  VARCHAR(500),
                tags       JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))
        conn.commit()

    print("Migration complete: project_notes table created.")