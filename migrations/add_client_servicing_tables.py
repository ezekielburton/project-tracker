"""
Migration: create the Client Servicing module's tables — client_servicing
(one row per project, the CS master-sheet fields) and
client_servicing_scopes (CS's own scope option list).
Run once: python migrations/add_client_servicing_tables.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur  = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS client_servicing_scopes (
        id         SERIAL PRIMARY KEY,
        name       VARCHAR(120) NOT NULL UNIQUE,
        active     BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS client_servicing (
        id               SERIAL PRIMARY KEY,
        project_id       INTEGER NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
        lpo              VARCHAR(120),
        store_location   VARCHAR(255),
        removal_date     DATE,
        invoice_month    VARCHAR(20),
        cost_to_client   NUMERIC(12, 2),
        inward_cost      NUMERIC(12, 2),
        scope_id         INTEGER REFERENCES client_servicing_scopes(id) ON DELETE SET NULL,
        priority         VARCHAR(120),
        created_at       TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

conn.commit()
cur.close()
conn.close()
print("Done — client_servicing and client_servicing_scopes tables created.")
