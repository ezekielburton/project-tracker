"""
Migration: create project_overlay_views table.
One row per (user, project) the first time that user opens the new
Detail overlay for that project — drives the "first-visit default is
Project Details, later visits default to Deliverables" behavior
(Projects Redesign Architecture.md §3). A marker, not a log: unique on
(user_id, project_id), one row ever per pair.
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
            CREATE TABLE IF NOT EXISTS project_overlay_views (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER NOT NULL REFERENCES users(id),
                project_id      INTEGER NOT NULL REFERENCES projects(id),
                first_viewed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (user_id, project_id)
            );
        """))
        conn.commit()

    print("Migration complete: project_overlay_views table created.")