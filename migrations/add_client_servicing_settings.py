"""
Migration: add client_servicing_settings table (Days Pending thresholds).
Run once: python add_client_servicing_settings.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_servicing_settings (
            id SERIAL PRIMARY KEY,
            days_green_max INTEGER NOT NULL DEFAULT 30,
            days_red_max INTEGER NOT NULL DEFAULT 60
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — client_servicing_settings table created.")
