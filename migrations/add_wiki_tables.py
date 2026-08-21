"""
Migration: create wiki_sections and wiki_articles tables.
Run once: python migrations/add_wiki_tables.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur  = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS wiki_sections (
        id             SERIAL PRIMARY KEY,
        title          VARCHAR(200) NOT NULL,
        slug           VARCHAR(200) NOT NULL UNIQUE,
        relevant_roles VARCHAR(200),
        sort_order     INTEGER NOT NULL DEFAULT 0,
        is_published   BOOLEAN NOT NULL DEFAULT FALSE,
        created_at     TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS wiki_articles (
        id            SERIAL PRIMARY KEY,
        section_id    INTEGER NOT NULL REFERENCES wiki_sections(id) ON DELETE CASCADE,
        title         VARCHAR(200) NOT NULL,
        slug          VARCHAR(200) NOT NULL,
        sections_json TEXT NOT NULL DEFAULT '[]',
        sort_order    INTEGER NOT NULL DEFAULT 0,
        is_published  BOOLEAN NOT NULL DEFAULT FALSE,
        created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

conn.commit()
cur.close()
conn.close()
print("Done — wiki_sections and wiki_articles tables created.")