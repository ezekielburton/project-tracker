"""
Migration: create user_table_layouts table.
Stores each user's personal column widths/order per table+view — silent,
ambient preference, never shared between users.
Run once from the project root: python migrations/add_user_table_layouts.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_table_layouts (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                table_key  VARCHAR(100) NOT NULL,
                layout     JSONB NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(user_id, table_key)
            );
        """))
        conn.commit()

    print("Migration complete: user_table_layouts table created.")