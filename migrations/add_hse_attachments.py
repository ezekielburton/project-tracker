"""
Migration: create hse_attachments — the record of which files an HSE entry
has on the NAS. The bytes live under /HSE; this table says where.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_attachments (
        id                SERIAL PRIMARY KEY,
        entry_id          INTEGER NOT NULL REFERENCES hse_entries(id) ON DELETE CASCADE,
        filename          VARCHAR(255) NOT NULL,
        original_filename VARCHAR(255) NOT NULL,
        file_type         VARCHAR(20) NOT NULL,
        nas_path          VARCHAR(1000) NOT NULL,
        uploaded_by_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
        uploaded_at       TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_attachments_entry ON hse_attachments (entry_id);")

conn.commit()
cur.close()
conn.close()
print("Done — hse_attachments table created.")
