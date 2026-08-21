"""
Migration: add notification_prefs column to users table.
Run once: python add_notification_prefs.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur  = conn.cursor()
    # VARCHAR(2000) is enough to hold a JSON object with all pref keys
    cur.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS notification_prefs VARCHAR(2000);
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — notification_prefs column added to users.")
