"""
Migration: wiki_article_views, one row per person reading an article (at most
once a day), for read counts, Most read and the Adoption page.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS wiki_article_views (
        id         SERIAL PRIMARY KEY,
        article_id INTEGER NOT NULL REFERENCES wiki_articles(id) ON DELETE CASCADE,
        user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
        source     VARCHAR(10) NOT NULL,
        viewed_at  TIMESTAMP NOT NULL
    );
""")
cur.execute("""
    CREATE INDEX IF NOT EXISTS ix_wiki_article_views_article_viewed
        ON wiki_article_views (article_id, viewed_at);
""")
conn.commit()
cur.close()
conn.close()
print("Done: wiki_article_views created.")
