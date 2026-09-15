"""
Migration: create the HSE & Compliance module's tables — the entry table
every register shares, the officer's own reference lists, assets and
people, the recurring schedule behind the calendar, and the per-register
ref counter.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_reference (
        id         SERIAL PRIMARY KEY,
        kind       VARCHAR(40) NOT NULL,
        label      VARCHAR(160) NOT NULL,
        active     BOOLEAN NOT NULL DEFAULT TRUE,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_hse_reference_kind_label UNIQUE (kind, label)
    );
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_reference_kind ON hse_reference (kind);")

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_assets (
        id         SERIAL PRIMARY KEY,
        kind       VARCHAR(20) NOT NULL,
        label      VARCHAR(160) NOT NULL,
        ref        VARCHAR(80),
        active     BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_assets_kind ON hse_assets (kind);")

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_people (
        id               SERIAL PRIMARY KEY,
        name             VARCHAR(160) NOT NULL,
        role             VARCHAR(160),
        organisation     VARCHAR(160),
        is_external      BOOLEAN NOT NULL DEFAULT FALSE,
        can_hold_actions BOOLEAN NOT NULL DEFAULT FALSE,
        email            VARCHAR(200),
        phone            VARCHAR(50),
        user_id          INTEGER REFERENCES users(id) ON DELETE SET NULL,
        active           BOOLEAN NOT NULL DEFAULT TRUE,
        created_at       TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_schedules (
        id           SERIAL PRIMARY KEY,
        register     VARCHAR(40) NOT NULL,
        label        VARCHAR(200) NOT NULL,
        frequency    VARCHAR(20) NOT NULL,
        interval     INTEGER NOT NULL DEFAULT 1,
        weekday      INTEGER,
        day_of_month INTEGER,
        starts_on    DATE NOT NULL,
        ends_on      DATE,
        owner_id     INTEGER REFERENCES hse_people(id) ON DELETE SET NULL,
        active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at   TIMESTAMP NOT NULL DEFAULT NOW()
    );
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_schedules_register ON hse_schedules (register);")

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_schedule_assets (
        schedule_id INTEGER NOT NULL REFERENCES hse_schedules(id) ON DELETE CASCADE,
        asset_id    INTEGER NOT NULL REFERENCES hse_assets(id) ON DELETE CASCADE,
        PRIMARY KEY (schedule_id, asset_id)
    );
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_entries (
        id              SERIAL PRIMARY KEY,
        register        VARCHAR(40) NOT NULL,
        ref             VARCHAR(40) NOT NULL,
        entry_date      DATE NOT NULL,
        status          VARCHAR(40),
        severity        VARCHAR(20),
        closed_at       DATE,
        due_at          DATE,
        location_id     INTEGER REFERENCES hse_reference(id) ON DELETE SET NULL,
        department_id   INTEGER REFERENCES hse_reference(id) ON DELETE SET NULL,
        asset_id        INTEGER REFERENCES hse_assets(id) ON DELETE SET NULL,
        reported_by_id  INTEGER REFERENCES hse_people(id) ON DELETE SET NULL,
        assigned_to_id  INTEGER REFERENCES hse_people(id) ON DELETE SET NULL,
        waiting_on_id   INTEGER REFERENCES hse_people(id) ON DELETE SET NULL,
        waiting_since   DATE,
        schedule_id     INTEGER REFERENCES hse_schedules(id) ON DELETE SET NULL,
        occurrence_date DATE,
        created_by_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
        data            JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_hse_entries_register_ref UNIQUE (register, ref)
    );
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_entries_register ON hse_entries (register);")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_entries_register_status ON hse_entries (register, status);")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_entries_register_date ON hse_entries (register, entry_date);")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_entries_due_at ON hse_entries (due_at);")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_entries_occurrence ON hse_entries (schedule_id, occurrence_date);")

cur.execute("""
    CREATE TABLE IF NOT EXISTS hse_ref_counters (
        register   VARCHAR(40) PRIMARY KEY,
        last_value INTEGER NOT NULL DEFAULT 0
    );
""")

conn.commit()
cur.close()
conn.close()
print("Done — HSE tables created.")
