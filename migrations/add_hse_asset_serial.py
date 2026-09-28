"""
Migration: hse_assets.serial_no — a machine's serial number, stored once on
the asset and shown on the machine registers' entries.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()

cur.execute("""
    ALTER TABLE hse_assets
    ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
""")

conn.commit()
cur.close()
conn.close()
print("Done — hse_assets.serial_no added.")
