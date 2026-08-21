"""
Migration: create blog_posts and blog_comments tables.
Run once:  python add_blog_tables.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur  = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS blog_posts (
        id            SERIAL PRIMARY KEY,
        title         VARCHAR(200) NOT NULL,
        version_tag   VARCHAR(80),
        author_id     INTEGER NOT NULL REFERENCES users(id),
        is_published  BOOLEAN NOT NULL DEFAULT FALSE,
        created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
        published_at  TIMESTAMP,
        sections_json TEXT NOT NULL DEFAULT '[]'
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS blog_comments (
        id         SERIAL PRIMARY KEY,
        post_id    INTEGER NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        body       TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

conn.commit()
cur.close()
conn.close()
print("Done — blog_posts and blog_comments tables created.")
