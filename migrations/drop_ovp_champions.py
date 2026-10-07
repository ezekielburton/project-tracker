"""
Migration: drop the ovp_champions table.
Run via: python migrate.py (NOT directly - see migrate.py at project root)

Safe to re-run: DROP TABLE uses IF EXISTS.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS ovp_champions;")

    conn.commit()
    cur.close()
    conn.close()
    print("Done - ovp_champions table dropped.")
