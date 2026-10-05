"""
Migration: create pending_nas_uploads — files kept on the server while the
NAS was down, waiting for nas_outbox_flush.py to push them.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS pending_nas_uploads (
        id         SERIAL PRIMARY KEY,
        nas_path   VARCHAR(1000) NOT NULL UNIQUE,
        local_name VARCHAR(64) NOT NULL,
        attempts   INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

conn.commit()
cur.close()
conn.close()
print("Done — pending_nas_uploads table created.")
