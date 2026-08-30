"""
Migration: add theme_preference column to users table.
Run once: python add_theme_preference.py
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
        ADD COLUMN IF NOT EXISTS theme_preference VARCHAR(10);
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — theme_preference column added to users.")
