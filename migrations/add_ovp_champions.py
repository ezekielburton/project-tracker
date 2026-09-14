"""
Migration: create ovp_champions table (the weekly-rotating OVP champion
designation — one row per week, history retained).
Run via: python migrate.py (NOT directly - see migrate.py at project root)

This script is applied, and its filename recorded in the schema_migrations
table, by migrate.py. Running it a second time is harmless because the
statement below uses IF NOT EXISTS.
"""

import sys, os
# Add the project root (one level up from migrations/) to the import path,
# so "from app import ..." below can find the app package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ovp_champions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),   -- matches OvpChampion.user_id
            week_start DATE NOT NULL UNIQUE,                     -- the Monday of the week; one champion per week
            set_by_id INTEGER REFERENCES users(id),          -- the admin who assigned it
            created_at TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Done - ovp_champions table created.")
