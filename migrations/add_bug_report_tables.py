"""
Migration: create bug_reports and bug_report_comments tables.
Run once: python migrations/add_bug_report_tables.py
"""

import psycopg2
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur  = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS bug_reports (
        id              SERIAL PRIMARY KEY,
        title           VARCHAR(200) NOT NULL,
        description     TEXT NOT NULL,
        submitted_by_id INTEGER NOT NULL REFERENCES users(id),
        status          VARCHAR(50) NOT NULL DEFAULT 'in_queue',
        created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS bug_report_comments (
        id         SERIAL PRIMARY KEY,
        bug_id     INTEGER NOT NULL REFERENCES bug_reports(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        parent_id  INTEGER REFERENCES bug_report_comments(id) ON DELETE CASCADE,
        body       TEXT NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
    );
""")

conn.commit()
cur.close()
conn.close()
print("Done — bug_reports and bug_report_comments tables created.")
