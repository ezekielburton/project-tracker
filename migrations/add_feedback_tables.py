"""
Migration: create feature_requests, feature_request_upvotes, feature_request_comments.
Run once: python migrations/add_feedback_tables.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur  = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS feature_requests (
        id              SERIAL PRIMARY KEY,
        title           VARCHAR(200) NOT NULL,
        description     TEXT NOT NULL,
        submitted_by_id INTEGER NOT NULL REFERENCES users(id),
        status          VARCHAR(50) NOT NULL DEFAULT 'requested',
        created_at      TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS feature_request_upvotes (
        id         SERIAL PRIMARY KEY,
        feature_id INTEGER NOT NULL REFERENCES feature_requests(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(feature_id, user_id)
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS feature_request_comments (
        id         SERIAL PRIMARY KEY,
        feature_id INTEGER NOT NULL REFERENCES feature_requests(id) ON DELETE CASCADE,
        user_id    INTEGER NOT NULL REFERENCES users(id),
        parent_id  INTEGER REFERENCES feature_request_comments(id) ON DELETE CASCADE,
        body       TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

conn.commit()
cur.close()
conn.close()
print("Done — feature_requests, feature_request_upvotes, feature_request_comments created.")
