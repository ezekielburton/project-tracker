"""
Migration: add profile page fields to users table.
Run once: python add_profile_fields.py
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
        ADD COLUMN IF NOT EXISTS bio TEXT,
        ADD COLUMN IF NOT EXISTS avatar_filename VARCHAR(255),
        ADD COLUMN IF NOT EXISTS banner_filename VARCHAR(255),
        ADD COLUMN IF NOT EXISTS favorite_food VARCHAR(100),
        ADD COLUMN IF NOT EXISTS birthday DATE;
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — bio, avatar_filename, banner_filename, favorite_food, birthday columns added to users.")