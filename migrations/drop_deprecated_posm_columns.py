"""
Migration: drop deprecated POSM tracking columns from projects table.
These were superseded by ProjectPosmChannel per-channel tracking.
Run once from the project root:  python migrations/drop_deprecated_posm_columns.py
"""

import sys, os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE projects DROP COLUMN IF EXISTS posm_started;"))
        conn.execute(text("ALTER TABLE projects DROP COLUMN IF EXISTS posm_started_at;"))
        conn.execute(text("ALTER TABLE projects DROP COLUMN IF EXISTS concept_kv_revision_count;"))
        conn.commit()

    print("Migration complete: deprecated POSM columns dropped.")