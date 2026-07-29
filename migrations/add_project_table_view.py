"""
Migration: create project_table_views table.
Stores each user's personal views and filtering options.
Run via migrations.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_table_views (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                name       VARCHAR(100) NOT NULL,
                base_view  VARCHAR(20) NOT NULL,
                filters    JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))
        conn.commit()

    print("Migration complete: project_table_views table created.")