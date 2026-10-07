"""
Migration: system_incidents.title and .minutes (what happened and how long it
lasted); the note becomes optional.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    ALTER TABLE system_incidents ADD COLUMN IF NOT EXISTS title VARCHAR(120) NOT NULL DEFAULT '';
    ALTER TABLE system_incidents ADD COLUMN IF NOT EXISTS minutes INTEGER;
    ALTER TABLE system_incidents ALTER COLUMN note DROP NOT NULL;
""")
conn.commit()
cur.close()
conn.close()
print("Done: system_incidents.title, .minutes added; note optional.")
