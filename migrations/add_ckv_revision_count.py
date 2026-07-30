"""
Migration: add ckv_revision_count column to projects table.
Tracks how many client revision rounds the Concept & KV deck has gone through.
Separate from concept_kv_revision_count (which is a POSM snapshot, not a counter).
Run once from the project root: python add_ckv_revision_count.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        # Add the counter column — default 0 so all existing projects start clean
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS ckv_revision_count INTEGER DEFAULT 0;
        """))
        conn.commit()

    print("Migration complete: ckv_revision_count column added to projects.")