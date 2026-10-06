"""
Migration: Reports module tables: report_runs (every generated PDF),
report_recipients and report_auto_send.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS report_runs (
        id           SERIAL PRIMARY KEY,
        report       VARCHAR(30)  NOT NULL,
        period_kind  VARCHAR(10)  NOT NULL,
        period_start DATE         NOT NULL,
        period_end   DATE         NOT NULL,
        made_at      TIMESTAMP    NOT NULL,
        made_by_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
        file_name    VARCHAR(255) NOT NULL,
        file_size    INTEGER      NOT NULL DEFAULT 0,
        status       VARCHAR(20)  NOT NULL DEFAULT 'generated',
        sent_at      TIMESTAMP,
        sent_to      JSON,
        error        TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_report_runs_period ON report_runs (period_kind, period_start);

    CREATE TABLE IF NOT EXISTS report_recipients (
        id         SERIAL PRIMARY KEY,
        report     VARCHAR(30) NOT NULL,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_report_recipients_report_user UNIQUE (report, user_id)
    );

    CREATE TABLE IF NOT EXISTS report_auto_send (
        report      VARCHAR(30) NOT NULL,
        period_kind VARCHAR(10) NOT NULL,
        enabled     BOOLEAN NOT NULL DEFAULT TRUE,
        PRIMARY KEY (report, period_kind)
    );
""")
conn.commit()
cur.close()
conn.close()
print("Done: report_runs, report_recipients, report_auto_send created.")
