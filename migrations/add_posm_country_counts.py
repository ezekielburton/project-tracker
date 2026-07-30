"""
Migration: add posm_country_revision_counts JSON column to projects.
Stores per-country POSM revision counters for non-UAE Gulf regions
(mirrors pc.posm_revision_count for UAE customers).
Run once from the project root:  python add_posm_country_counts.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS posm_country_revision_counts JSONB;"
        ))
        conn.commit()

    print("Migration complete: posm_country_revision_counts column added.")
