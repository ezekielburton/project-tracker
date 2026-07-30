"""
Migration: add design_deadline_time to deliverables and project_customers
Run once: python add_design_deadline_time.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute("""
    ALTER TABLE deliverables
    ADD COLUMN IF NOT EXISTS design_deadline_time TIME;
""")

cur.execute("""
    ALTER TABLE project_customers
    ADD COLUMN IF NOT EXISTS design_deadline_time TIME;
""")

cur.execute("""
    ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS concept_deadline_time TIME;
""")

conn.commit()
cur.close()
conn.close()
print("Done — design_deadline_time added to deliverables and project_customers; concept_deadline_time added to projects.")
