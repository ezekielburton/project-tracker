"""
Migration: add company_id and contact_id columns to projects table.
Run via: python migrate.py (NOT directly - see migrate.py at project root)

Adds the two Client Directory foreign keys that live on Project
(app/models/__init__.py). This runs AFTER add_client_directory.py, since
these columns reference companies.id and contacts.id - those tables must
already exist or Postgres will reject the REFERENCES clause. migrate.py runs
pending migrations in filename order, and "add_client_directory.py" sorts
before "add_project_client_fields.py" alphabetically, so that ordering is
automatic here - but it's worth knowing this file has a hard dependency on
the previous one, not just an alphabetical coincidence.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    # Both columns are nullable and have no ON DELETE clause, matching the
    # nullable=True FK columns declared on Project in models - no default
    # value is needed since NULL is itself the valid "not set yet" state for
    # every existing project.
    cur.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id);
    """)

    cur.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS contact_id INTEGER REFERENCES contacts(id);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Done - company_id and contact_id columns added to projects.")
