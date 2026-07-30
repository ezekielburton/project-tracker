"""
Migration: add secondary CS tables
Run once from the project root:  python add_secondary_cs.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_secondary_cs (
                id          SERIAL PRIMARY KEY,
                project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                added_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                added_at    TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                CONSTRAINT uq_project_secondary_cs UNIQUE (project_id, user_id)
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_secondary_cs_regions (
                id          SERIAL PRIMARY KEY,
                project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                region      VARCHAR(20) NOT NULL,
                CONSTRAINT uq_project_secondary_cs_region UNIQUE (project_id, user_id, region)
            );
        """))

        conn.commit()

    print("Migration complete: project_secondary_cs and project_secondary_cs_regions tables created.")
