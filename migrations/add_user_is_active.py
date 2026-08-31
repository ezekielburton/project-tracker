"""
Migration: add is_active column to users table.
Run once: python add_user_is_active.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur  = conn.cursor()
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — is_active column added to users.")