"""
Migration: system_samples (the collector's history) and app_log_events
(errors, warnings and worker starts read from the app log).
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS system_samples (
        id     BIGSERIAL PRIMARY KEY,
        ts     TIMESTAMP        NOT NULL,
        metric VARCHAR(80)      NOT NULL,
        value  DOUBLE PRECISION NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_system_samples_ts ON system_samples (ts);
    CREATE INDEX IF NOT EXISTS ix_system_samples_metric_ts ON system_samples (metric, ts);

    CREATE TABLE IF NOT EXISTS app_log_events (
        id        BIGSERIAL PRIMARY KEY,
        ts        TIMESTAMP    NOT NULL,
        level     VARCHAR(10)  NOT NULL,
        source    VARCHAR(120) NOT NULL,
        signature VARCHAR(200) NOT NULL,
        message   TEXT         NOT NULL,
        detail    TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_app_log_events_ts ON app_log_events (ts);
    CREATE INDEX IF NOT EXISTS ix_app_log_events_signature_ts ON app_log_events (signature, ts);
""")
conn.commit()
cur.close()
conn.close()
print("Done: system_samples, app_log_events created.")
