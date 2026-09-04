"""
Migration: add installation-calendar fields to client_servicing.
Run once: python add_client_servicing_calendar_fields.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur  = conn.cursor()
    cur.execute("""
        ALTER TABLE client_servicing
        ADD COLUMN IF NOT EXISTS risk VARCHAR(20),
        ADD COLUMN IF NOT EXISTS next_action VARCHAR(255),
        ADD COLUMN IF NOT EXISTS action_owner VARCHAR(120);
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — calendar fields added to client_servicing.")
