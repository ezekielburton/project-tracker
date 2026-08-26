"""
Migration: create project_edit_access_requests table (Request Editing
Access — a designer's self-service request for full deliverable-management
+ status-override rights on one live project they're assigned to, approved
or denied by that project's CS Lead/Secondary CS/management/admin).
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
        CREATE TABLE IF NOT EXISTS project_edit_access_requests (
            id SERIAL PRIMARY KEY,
            project_id INTEGER NOT NULL REFERENCES projects(id),   -- matches ProjectEditAccessRequest.project_id
            user_id INTEGER NOT NULL REFERENCES users(id),          -- matches ProjectEditAccessRequest.user_id (the requesting designer)
            status VARCHAR(20) NOT NULL DEFAULT 'pending',          -- 'pending' | 'approved' | 'denied'
            requested_at TIMESTAMP NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMP,
            decided_by_id INTEGER REFERENCES users(id),
            -- One request row per (project, designer) — a denied request is
            -- reset and reused on re-request rather than getting a second
            -- row, so this constraint never needs working around. Matches
            -- the model's own db.UniqueConstraint.
            CONSTRAINT uq_project_edit_access_requests_project_user UNIQUE (project_id, user_id)
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Done - project_edit_access_requests table created.")
