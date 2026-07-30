"""
Migration: create site_visits table.
Structured record of a technical person's site visit (who/project/when),
so the dashboard can compute + show when a technical designer is out of
the building. Structured rather than a freeform note precisely because
the dashboard needs real dates/times, per Projects Redesign Architecture.md §11.
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
            CREATE TABLE IF NOT EXISTS site_visits (
                id         SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                user_id    INTEGER NOT NULL REFERENCES users(id),
                start_at   TIMESTAMP NOT NULL,
                end_at     TIMESTAMP NOT NULL,
                location   VARCHAR(255),
                notes      TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))
        conn.commit()

    print("Migration complete: site_visits table created.")