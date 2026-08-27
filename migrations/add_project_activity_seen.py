"""
Migration: create project_activity_seen table (the Projects table's
per-user "update"/"chat" unread dots — two independent watermarks per
(user, project), so staff can clear a new-update dot without that also
silently clearing an unread chat dot, and vice versa).
Run via: python migrate.py (NOT directly - see migrate.py at project root)

This script is applied, and its filename recorded in the schema_migrations
table, by migrate.py. Running it a second time is harmless because the
statement below uses IF NOT EXISTS.
"""

import sys, os
# Add the project root (one level up from migrations/) to the import path,
# so "from app import ..." below can find the app package. Needed because this
# file lives in migrations/, not the root, but still needs to build the Flask
# app to get a real DB connection via SQLAlchemy's engine.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    # raw_connection() hands back the underlying DBAPI (psycopg2) connection
    # instead of going through the ORM/session - appropriate here since we're
    # running plain DDL (CREATE TABLE), not inserting/querying model objects.
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_activity_seen (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),      -- matches ProjectActivitySeen.user_id
            project_id INTEGER NOT NULL REFERENCES projects(id), -- matches ProjectActivitySeen.project_id
            last_seen_update_at TIMESTAMP,                       -- advanced by opening the project overlay at all
            last_seen_chat_at TIMESTAMP,                         -- advanced only by opening the Chat drawer
            -- One row per (user, project) — mark_project_activity_seen()
            -- in core/shared/lib/utils.py upserts against this rather than
            -- ever inserting a second row for the same pair. Matches the
            -- model's own db.UniqueConstraint.
            CONSTRAINT uq_project_activity_seen_user_project UNIQUE (user_id, project_id)
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Done - project_activity_seen table created.")
