"""
Migration: add changes JSONB column to activity_logs table.
Stores the structured field-level diff for granular activity logging
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
            ALTER TABLE activity_logs
            ADD COLUMN IF NOT EXISTS changes JSONB;
        """))
        conn.commit()

    print("Migration Complete: changes column added to activity_logs.")