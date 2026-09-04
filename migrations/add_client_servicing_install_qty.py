"""
Migration: add install_qty to client_servicing.
Run once: python add_client_servicing_install_qty.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur  = conn.cursor()
    cur.execute("ALTER TABLE client_servicing ADD COLUMN IF NOT EXISTS install_qty INTEGER;")
    conn.commit()
    cur.close()
    conn.close()
    print("Done — install_qty added to client_servicing.")
