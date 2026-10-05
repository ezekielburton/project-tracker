"""
Migration: the org model. Adds job_roles and the user fields department,
job_role_id, seniority, reports_to_id and is_admin.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS job_roles (
        id          SERIAL PRIMARY KEY,
        department  VARCHAR(40),
        title       VARCHAR(100) NOT NULL,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        CONSTRAINT uq_job_roles_department_title UNIQUE NULLS NOT DISTINCT (department, title)
    );
""")
cur.execute("""
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS department    VARCHAR(40),
        ADD COLUMN IF NOT EXISTS job_role_id   INTEGER REFERENCES job_roles(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS seniority     VARCHAR(20) NOT NULL DEFAULT 'none',
        ADD COLUMN IF NOT EXISTS reports_to_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS is_admin      BOOLEAN NOT NULL DEFAULT FALSE;
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_users_reports_to_id ON users (reports_to_id);")
conn.commit()
cur.close()
conn.close()
print("Done: job_roles created; org fields added to users.")
