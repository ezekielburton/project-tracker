"""Migration: add project_note_reactions table — one reaction per person per
message, enforced by the unique (note_id, user_id) constraint. Run via migrate.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_note_reactions (
                id SERIAL PRIMARY KEY,
                note_id INTEGER NOT NULL REFERENCES project_notes(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                emoji VARCHAR(16) NOT NULL,
                created_at TIMESTAMP,
                CONSTRAINT uq_project_note_reactions_note_user UNIQUE (note_id, user_id)
            );
        """))
        conn.commit()

    print("Migration complete: project_note_reactions table created.")
