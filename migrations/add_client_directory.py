"""
Migration: create companies and contacts tables (Client Directory).
Run via: python migrate.py (NOT directly - see migrate.py at project root)

This script is applied, and its filename recorded in the schema_migrations
table, by migrate.py. Running it a second time is harmless because every
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

    # companies must be created first: contacts.company_id below has a
    # REFERENCES companies(id) clause, and Postgres will refuse to create a
    # foreign key that points at a table which doesn't exist yet.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,                 -- auto-incrementing integer PK
            name VARCHAR(200) NOT NULL UNIQUE,      -- matches Company.name: required + unique
            aliases VARCHAR(500)                    -- matches Company.aliases: optional (no NOT NULL)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,             -- matches Contact.name: required
            phone VARCHAR(50),                      -- matches Contact.phone: optional
            email VARCHAR(200),                     -- matches Contact.email: optional
            company_id INTEGER NOT NULL REFERENCES companies(id)
            -- ^ NOT NULL because a contact always belongs to a company (matches
            -- the model's nullable=False), and REFERENCES companies(id) is what
            -- actually creates the foreign key constraint in Postgres - this is
            -- the DB-level enforcement backing SQLAlchemy's db.ForeignKey(...).
            --
            -- Deliberately no "ON DELETE CASCADE" here: deletion cascading is
            -- handled purely by SQLAlchemy's cascade='all, delete-orphan' on the
            -- Company.contacts relationship (see models). That mirrors how the
            -- existing Project -> ProjectCustomer/Deliverable cascades work in
            -- this codebase - ORM-only, no DB-level cascade - so this stays
            -- consistent with that precedent rather than introducing a new,
            -- differently-behaved cascade style.
        );
    """)

    conn.commit()  # writes both CREATE TABLE statements to the DB in one transaction
    cur.close()
    conn.close()
    print("Done - companies and contacts tables created.")
