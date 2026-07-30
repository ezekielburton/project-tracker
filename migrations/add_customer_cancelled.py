"""
Migration: add cancelled colmn to project_customers table
Run once from the project root: python migratons/add_customer_cancelled.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE project_customers
            ADD COLUMN IF NOT EXISTS cancelled BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.commit()

    print("Migration complete: cancelled column added to project_customers.")

    