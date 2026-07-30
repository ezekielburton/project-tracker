"""
Migration: add posm_country column for Gulf region-based POSM tracking.
Run once from the project root:  python add_gulf_posm.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        # Gulf projects submit POSM per country/region rather than per customer
        conn.execute(text("ALTER TABLE project_submissions ADD COLUMN IF NOT EXISTS posm_country VARCHAR(50);"))
        conn.execute(text("ALTER TABLE project_revisions ADD COLUMN IF NOT EXISTS posm_country VARCHAR(50);"))
        conn.commit()

    print("Migration complete: posm_country columns added.")
