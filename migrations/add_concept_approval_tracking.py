"""
Migration: add concept_approved_at / concept_approved_by_id columns to projects.

These two columns already exist in the Project model (app/models/__init__.py,
Concept & KV approval tracking section) but were apparently never migrated
into the actual database — discovered via a crash on /api/projects/<id>/poll
(project_detail_poll in app/routes/api.py) when SQLAlchemy tried to SELECT
columns that don't exist yet. Unrelated to the achievement system work done
the same session this was found in.

Run once: python migrations/add_concept_approval_tracking.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()
    cur.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS concept_approved_at TIMESTAMP,
        ADD COLUMN IF NOT EXISTS concept_approved_by_id INTEGER REFERENCES users(id);
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — concept_approved_at, concept_approved_by_id columns added to projects.")
