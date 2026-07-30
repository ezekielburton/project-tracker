"""
Migration: Add Cancel/Archive lifecycle fields to projects table.
Cancel is reversible (reactivate clears these back to NULL/FALSE) and
logged/visible to admin+management on the dashboard. Delete (is_deleted/
deleted_at/deleted_by_id) is the separate, rare, admin-only
permanent removal from the archive.

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
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS cancel_reason TEXT;
        """))
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP;
        """))
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS cancelled_by_id INTEGER REFERENCES users(id);
        """))
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
        """))
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS deleted_by_id INTEGER REFERENCES users(id);
        """))
        conn.commit()

    print("Migration complete: cancel + soft-delete fields added to projects.")