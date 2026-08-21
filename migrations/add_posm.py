"""
Migration: add POSM phase tracking columns.
Run once from the project root:  python add_posm.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        # Project: POSM phase flags
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS posm_started BOOLEAN NOT NULL DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS posm_started_at TIMESTAMP;"))
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS concept_kv_revision_count INTEGER;"))

        # ProjectCustomer: per-customer POSM revision counter
        conn.execute(text("ALTER TABLE project_customers ADD COLUMN IF NOT EXISTS posm_revision_count INTEGER NOT NULL DEFAULT 0;"))

        # ProjectSubmission: which customer + which phase
        conn.execute(text("ALTER TABLE project_submissions ADD COLUMN IF NOT EXISTS posm_customer_id INTEGER REFERENCES project_customers(id);"))
        conn.execute(text("ALTER TABLE project_submissions ADD COLUMN IF NOT EXISTS phase VARCHAR(20) NOT NULL DEFAULT 'concept_kv';"))

        # ProjectRevision: which customer this revision targeted (null = concept/KV phase)
        conn.execute(text("ALTER TABLE project_revisions ADD COLUMN IF NOT EXISTS posm_customer_id INTEGER REFERENCES project_customers(id);"))

        conn.commit()

    print("Migration complete: POSM columns added.")
