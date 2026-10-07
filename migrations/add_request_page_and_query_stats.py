"""
Migration: request_metrics.page (a whole HTML page, for page-load times) and
query_stat_samples (hourly pg_stat_statements totals, for the 24-hour
slowest-queries list).
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    ALTER TABLE request_metrics ADD COLUMN IF NOT EXISTS page BOOLEAN NOT NULL DEFAULT false;

    CREATE TABLE IF NOT EXISTS query_stat_samples (
        id       BIGSERIAL PRIMARY KEY,
        ts       TIMESTAMP        NOT NULL,
        queryid  BIGINT           NOT NULL,
        calls    BIGINT           NOT NULL,
        total_ms DOUBLE PRECISION NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_query_stat_samples_ts ON query_stat_samples (ts);
""")
conn.commit()
cur.close()
conn.close()
print("Done: request_metrics.page, query_stat_samples created.")
