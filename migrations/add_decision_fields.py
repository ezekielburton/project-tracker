"""
Migration: add decision-flag fields to projects table
Run once: python migrate.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur  = conn.cursor()
    cur.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS decision_needed BOOLEAN DEFAULT FALSE;
    """)
    cur.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS decision_raised_by_id INTEGER REFERENCES users(id);
    """)
    cur.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS decision_raised_at TIMESTAMP WITHOUT TIME ZONE;
    """)
    cur.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS decision_note TEXT;
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — decision fields added to projects.")