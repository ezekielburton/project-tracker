"""
Migration: hse_entries.performed_by_id — who did the work (treated,
inspected, repaired, trained), so Reported by can mean the reporter on
every register.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    ALTER TABLE hse_entries
    ADD COLUMN IF NOT EXISTS performed_by_id INTEGER
        REFERENCES hse_people(id) ON DELETE SET NULL;
""")
conn.commit()
cur.close()
conn.close()
print("Done — hse_entries.performed_by_id added.")
