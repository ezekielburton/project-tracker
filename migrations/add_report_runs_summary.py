"""
Migration: report_runs.summary, the email's headline numbers (score, change,
people with no activity) kept with the run, so a resend matches the PDF.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("ALTER TABLE report_runs ADD COLUMN IF NOT EXISTS summary JSON;")
conn.commit()
cur.close()
conn.close()
print("Done: report_runs.summary added.")
