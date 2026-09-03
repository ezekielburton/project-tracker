"""
Migration: create the Digital Innovation module's tables (di_projects,
di_features, di_feature_steps, di_step_templates, di_cost_entries,
di_settings, di_period_snapshots, di_intake_items) and seed the one
permanent board ("OVP", is_permanent=TRUE) that the module's Incoming
tray and the app's feedback-intake seam both hand items to.
Run once: python migrations/add_digital_innovation_tables.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur  = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_projects (
        id                 SERIAL PRIMARY KEY,
        name               VARCHAR(200) NOT NULL,
        client_label       VARCHAR(200),
        colour             VARCHAR(20),
        client_charge      FLOAT,
        lifecycle          VARCHAR(20) NOT NULL DEFAULT 'active',
        closed_at          TIMESTAMP,
        is_permanent       BOOLEAN NOT NULL DEFAULT FALSE,
        linked_project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        created_at         TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_features (
        id             SERIAL PRIMARY KEY,
        di_project_id  INTEGER NOT NULL REFERENCES di_projects(id) ON DELETE CASCADE,
        name           VARCHAR(200) NOT NULL,
        status         VARCHAR(30) NOT NULL DEFAULT 'researching',
        projected_date DATE,
        closed_at      TIMESTAMP,
        sort_order     INTEGER NOT NULL DEFAULT 0,
        created_at     TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_feature_steps (
        id            SERIAL PRIMARY KEY,
        di_feature_id INTEGER NOT NULL REFERENCES di_features(id) ON DELETE CASCADE,
        stage         VARCHAR(30) NOT NULL,
        label         VARCHAR(200) NOT NULL,
        is_done       BOOLEAN NOT NULL DEFAULT FALSE,
        sort_order    INTEGER NOT NULL DEFAULT 0
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_step_templates (
        id         SERIAL PRIMARY KEY,
        stage      VARCHAR(30) NOT NULL,
        label      VARCHAR(200) NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_cost_entries (
        id            SERIAL PRIMARY KEY,
        di_project_id INTEGER NOT NULL REFERENCES di_projects(id) ON DELETE CASCADE,
        date          DATE NOT NULL,
        type          VARCHAR(20) NOT NULL,
        di_feature_id INTEGER REFERENCES di_features(id) ON DELETE SET NULL,
        description   VARCHAR(255),
        amount        FLOAT NOT NULL,
        hours         FLOAT,
        created_at    TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_settings (
        id              SERIAL PRIMARY KEY,
        dev_hourly_rate FLOAT NOT NULL DEFAULT 0,
        currency        VARCHAR(10) NOT NULL DEFAULT 'AED'
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_period_snapshots (
        id            SERIAL PRIMARY KEY,
        period_type   VARCHAR(10) NOT NULL,
        period_key    VARCHAR(20) NOT NULL,
        snapshot_data JSON NOT NULL,
        created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(period_type, period_key)
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS di_intake_items (
        id            SERIAL PRIMARY KEY,
        di_project_id INTEGER NOT NULL REFERENCES di_projects(id) ON DELETE CASCADE,
        source_type   VARCHAR(20) NOT NULL,
        source_ref    VARCHAR(100),
        title         VARCHAR(200) NOT NULL,
        description   TEXT,
        status        VARCHAR(20) NOT NULL DEFAULT 'pending',
        created_at    TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

# Seed the permanent OVP board — found later by is_permanent=TRUE, never by
# a hard-coded id. Guarded so re-running this migration is a no-op once
# it's already there.
cur.execute("""
    INSERT INTO di_projects (name, lifecycle, is_permanent)
    SELECT 'OVP', 'active', TRUE
    WHERE NOT EXISTS (SELECT 1 FROM di_projects WHERE is_permanent = TRUE);
""")

conn.commit()
cur.close()
conn.close()
print("Done — Digital Innovation tables created, permanent OVP board seeded.")