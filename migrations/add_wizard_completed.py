"""
Migration: add wizard_completed column to users table.
Run via: python migrate.py (NOT directory - see migrate.py at project root)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE USERS
        ADD COLUMN IF NOT EXISTS wizard_completed BOOLEAN DEFAULT FALSE;
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Done - wizard_completed column added to Users.")