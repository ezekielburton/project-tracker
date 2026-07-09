"""
Migration: add Client Directory detail-view fields to clients and contacts.

The directory page's wireframe calls for fields beyond what the original
backend session built. Since the standalone Company model was retired and
Client now plays that role (see retire_company_directory.py), these columns
go on clients, not a separate table:

  - clients.aliases              (was on the old Company model - re-added
                                   here now that Client has absorbed that role)
  - clients.office_location
  - clients.installation_locations
  - contacts.location

Run via: python migrate.py (NOT directly - see migrate.py at project root)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    # All four columns are nullable with no default - every existing Client/
    # Contact row predates this feature and simply has none of them set,
    # same reasoning as every other nullable-add-column migration in this
    # project (see e.g. add_wizard_completed.py's comments).
    cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS aliases VARCHAR(500);")
    cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS office_location VARCHAR(200);")
    cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS installation_locations TEXT;")
    cur.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS location VARCHAR(200);")

    conn.commit()
    cur.close()
    conn.close()
    print("Done - aliases/office_location/installation_locations added to clients, location added to contacts.")
