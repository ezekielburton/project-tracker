"""
Migration: add parent_id to blog_comments for threaded replies.
Run once: python migrations/add_blog_comment_replies.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur  = conn.cursor()

cur.execute("""
    ALTER TABLE blog_comments
    ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES blog_comments(id) ON DELETE CASCADE;
""")

conn.commit()
cur.close()
conn.close()
print("Done — parent_id added to blog_comments.")