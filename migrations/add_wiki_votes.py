"""
Migration: wiki_article_votes, each person's "Useful?" answer per article,
with an optional note on a "no".
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS wiki_article_votes (
        id         SERIAL PRIMARY KEY,
        article_id INTEGER NOT NULL REFERENCES wiki_articles(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        helpful    BOOLEAN NOT NULL,
        note       TEXT,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_wiki_article_votes_article_user UNIQUE (article_id, user_id)
    );
""")
conn.commit()
cur.close()
conn.close()
print("Done: wiki_article_votes created.")
