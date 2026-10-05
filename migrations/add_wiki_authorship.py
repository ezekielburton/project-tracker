"""
Migration: wiki_articles.created_by_id, updated_by_id and reviewed_at.
Existing articles were all written by the wiki's author: they get that account
as author and updater, and their last update as their review date.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

AUTHOR_EMAIL = 'ezekiel@vitamin.works'

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    ALTER TABLE wiki_articles
        ADD COLUMN IF NOT EXISTS created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS updated_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;
""")

cur.execute("SELECT id FROM users WHERE lower(email) = %s", (AUTHOR_EMAIL,))
row = cur.fetchone()
if row is None:
    # Fall back to the only admin; with none or several, stop rather than guess.
    cur.execute("SELECT id FROM users WHERE role = 'admin'")
    admins = cur.fetchall()
    if len(admins) != 1:
        conn.rollback()
        sys.exit(f"No user with email {AUTHOR_EMAIL} and {len(admins)} admins: set AUTHOR_EMAIL and re-run.")
    row = admins[0]
author_id = row[0]

# Raw SQL, so the ORM's onupdate leaves each article's Last updated date alone.
cur.execute("""
    UPDATE wiki_articles
       SET created_by_id = COALESCE(created_by_id, %s),
           updated_by_id = COALESCE(updated_by_id, %s),
           reviewed_at   = COALESCE(reviewed_at, updated_at)
""", (author_id, author_id))
conn.commit()
print(f"Done: authorship added, {cur.rowcount} article(s) credited to user {author_id}.")
cur.close()
conn.close()
