"""
Migration: add Project Owner + production only fields to projects table.
project_owner_id: the new Project Owner role, assigned at brief creation.
is_production_only: Standard project flagged at creation that starts in Pre-Production
skipping design
preproduction_requirements: CS's free text brief for Pre-Production, filled at creation
for production-only projects or when the phase opens for normal projects.

Run via migrate.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS project_owner_id INTEGER REFERENCES users(id);
            """))
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS is_production_only BOOLEAN NOT NULL DEFAULT FALSE;
            """))
        conn.execute(text("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS preproduction_requirements TEXT;
        """))
        conn.commit()

    print("Migration complete: project_owner_id, is_production_only, preproduction_requirements added to projects.")