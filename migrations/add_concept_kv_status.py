"""
Migration: add concept/KV status tracking columns.
Run once from the project root:  python add_concept_kv_status.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS concept_status VARCHAR(50);"))
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS kv_status VARCHAR(50);"))
        conn.execute(text("ALTER TABLE project_submissions ADD COLUMN IF NOT EXISTS includes_concept BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE project_submissions ADD COLUMN IF NOT EXISTS includes_kv BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE project_revisions ADD COLUMN IF NOT EXISTS includes_concept BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE project_revisions ADD COLUMN IF NOT EXISTS includes_kv BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.commit()

    print("Migration complete: concept/KV status columns added.")
