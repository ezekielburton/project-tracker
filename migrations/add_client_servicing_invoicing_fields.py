"""
Migration: add invoicing fields to client_servicing table.
Run once: python add_client_servicing_invoicing_fields.py
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
        ADD COLUMN IF NOT EXISTS lpo_date DATE,
        ADD COLUMN IF NOT EXISTS project_value NUMERIC(12, 2),
        ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(120),
        ADD COLUMN IF NOT EXISTS invoice_date DATE,
        ADD COLUMN IF NOT EXISTS invoice_amount NUMERIC(12, 2),
        ADD COLUMN IF NOT EXISTS gr_received BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS invoice_uploaded BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS validation_status VARCHAR(20);
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — invoicing fields added to client_servicing.")
