"""
Migration: remove deprecated columns from the database.
Run via: python migrate.py (NOT directory - see migrate.py at project root)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    cur.execute("""ALTER TABLE projects DROP COLUMN IF EXISTS decision_raised_by_id;""")
    cur.execute("""ALTER TABLE projects DROP COLUMN IF EXISTS decision_raised_at;""")
    cur.execute("""ALTER TABLE projects DROP COLUMN IF EXISTS decision_note;""")
    cur.execute("""ALTER TABLE projects DROP COLUMN IF EXISTS design_start_date;""")
    
    conn.commit()
    cur.close()
    conn.close()
    print("Done - safe columns dropped.")