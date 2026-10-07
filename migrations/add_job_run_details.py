"""
Migration: job_runs.details, what a job keeps with its run (sizes, paths,
counts, a report list).
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS details JSON;")
conn.commit()
cur.close()
conn.close()
print("Done: job_runs.details added.")
