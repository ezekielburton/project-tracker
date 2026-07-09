"""
Migration: retire the standalone Company table and repoint Contact at Client.

Reverses part of add_client_directory.py / add_project_client_fields.py.
After discussion (9 Jul 2026), the brief form's existing Client dropdown was
decided to already BE "the company" - so a separate Company table alongside
it was redundant. This migration:

  1. Drops contacts.company_id (and, with it, the FK constraint pointing at
     companies.id - dropping a column always drops any constraint that only
     exists because of that column).
  2. Drops projects.company_id the same way - it's redundant with client_id
     now that "company" and "client" are the same concept.
  3. Drops the companies table itself. Steps 1 and 2 must happen first:
     Postgres won't let you drop a table that other columns still have a
     REFERENCES pointing at, so this ordering is required, not stylistic.
  4. Adds contacts.client_id, NOT NULL, referencing clients(id).

Run via: python migrate.py (NOT directly - see migrate.py at project root)

Assumption worth calling out: step 4 adds client_id as NOT NULL with no
default, which requires the contacts table to be empty at migration time.
That's true here because this whole feature shipped this same week and
nothing in the app could create a Contact yet outside of a raw JSON POST
nobody was calling - if that's no longer true when this runs, Postgres will
raise a clear "column contains null values" error rather than silently
corrupting data, so this fails loudly instead of quietly.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    # 1. & 2. — drop the two columns that reference companies.id, freeing the
    # table up to be dropped in step 3. IF EXISTS makes each statement safe to
    # re-run if the migration ever partially applies and needs retrying.
    cur.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS company_id;")
    cur.execute("ALTER TABLE projects DROP COLUMN IF EXISTS company_id;")

    # 3. — nothing references companies anymore, so a plain DROP TABLE is
    # enough; no CASCADE needed (CASCADE would only be required if some other
    # constraint/view still depended on this table).
    cur.execute("DROP TABLE IF EXISTS companies;")

    # 4. — the real replacement: every Contact now belongs to a Client
    # directly. NOT NULL here matches Contact.client_id's nullable=False in
    # the model (see "DB Facts" convention throughout this codebase: the
    # Postgres constraint always mirrors the SQLAlchemy column definition).
    cur.execute("""
        ALTER TABLE contacts
        ADD COLUMN IF NOT EXISTS client_id INTEGER NOT NULL REFERENCES clients(id);
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Done - companies table dropped, contacts now reference clients directly.")
