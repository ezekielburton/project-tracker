"""
Migration: add cs_status to client_servicing table.
Run once: python add_client_servicing_cs_status.py
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
        ADD COLUMN IF NOT EXISTS cs_status VARCHAR(40);
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — cs_status added to client_servicing.")
