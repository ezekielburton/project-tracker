"""
Migration: system module tables: request_metrics, heartbeats, job_runs,
worker_stats, system_incidents. deploy_log is created by migrate.py itself.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS request_metrics (
        id           BIGSERIAL PRIMARY KEY,
        ts           TIMESTAMP    NOT NULL,
        method       VARCHAR(8)   NOT NULL,
        route        VARCHAR(200) NOT NULL,
        blueprint    VARCHAR(60),
        status       SMALLINT     NOT NULL,
        duration_ms  INTEGER      NOT NULL,
        queue_ms     INTEGER,
        user_id      INTEGER,
        emulating_id INTEGER
    );
    CREATE INDEX IF NOT EXISTS ix_request_metrics_ts ON request_metrics (ts);
    CREATE INDEX IF NOT EXISTS ix_request_metrics_errors ON request_metrics (ts) WHERE status >= 500;

    CREATE TABLE IF NOT EXISTS heartbeats (
        id SERIAL PRIMARY KEY,
        ts TIMESTAMP NOT NULL,
        ok BOOLEAN   NOT NULL,
        ms INTEGER
    );
    CREATE INDEX IF NOT EXISTS ix_heartbeats_ts ON heartbeats (ts);

    CREATE TABLE IF NOT EXISTS job_runs (
        id              SERIAL PRIMARY KEY,
        job             VARCHAR(60) NOT NULL,
        started_at      TIMESTAMP   NOT NULL,
        finished_at     TIMESTAMP   NOT NULL,
        result          VARCHAR(10) NOT NULL,
        message         TEXT,
        bytes_reclaimed BIGINT,
        run_by_id       INTEGER REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS ix_job_runs_job_started ON job_runs (job, started_at);

    CREATE TABLE IF NOT EXISTS worker_stats (
        pid        INTEGER PRIMARY KEY,
        sse_open   INTEGER   NOT NULL DEFAULT 0,
        updated_at TIMESTAMP NOT NULL
    );

    CREATE TABLE IF NOT EXISTS system_incidents (
        id            SERIAL PRIMARY KEY,
        happened_on   DATE      NOT NULL,
        note          TEXT      NOT NULL,
        created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        created_at    TIMESTAMP NOT NULL
    );
""")
conn.commit()
cur.close()
conn.close()
print("Done: request_metrics, heartbeats, job_runs, worker_stats, system_incidents created.")
