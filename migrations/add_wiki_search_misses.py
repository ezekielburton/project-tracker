"""
Migration: wiki_search_misses, one row per search that found nothing, for the
editor's Write next list.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS wiki_search_misses (
        id           SERIAL PRIMARY KEY,
        phrase       VARCHAR(200) NOT NULL,
        phrase_key   TEXT NOT NULL,
        user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
        note         TEXT,
        created_at   TIMESTAMP NOT NULL,
        dismissed_at TIMESTAMP
    );
""")
cur.execute("""
    CREATE INDEX IF NOT EXISTS ix_wiki_search_misses_phrase_key
        ON wiki_search_misses (phrase_key);
""")
conn.commit()
cur.close()
conn.close()
print("Done: wiki_search_misses created.")
