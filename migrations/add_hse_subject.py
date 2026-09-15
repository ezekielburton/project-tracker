"""
Migration: add hse_entries.subject_id — the person an entry is about, as
distinct from who filed it and who owns the follow-up.
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
    ADD COLUMN IF NOT EXISTS subject_id INTEGER
        REFERENCES hse_people(id) ON DELETE SET NULL;
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_entries_subject ON hse_entries (subject_id);")

conn.commit()
cur.close()
conn.close()
print("Done — hse_entries.subject_id added.")
