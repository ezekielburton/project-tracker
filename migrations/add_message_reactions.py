"""
Migration: add project_note_reactions table (M10 chat redesign — Phase 4,
21 Aug 2026) — the real backend behind the quick-react popover, which
until now only opened/closed as a UI-only provision.

One reaction per person per message: the unique constraint on
(note_id, user_id) is what makes toggle_reaction() safe to just check-
and-upsert instead of needing separate dedup logic — picking a different
emoji overwrites the row, picking the same emoji again is treated as
"remove."

note_id cascades on delete at the DB level — deleting a message should
silently drop its reactions with it, not orphan them. This is a backstop
for a delete that bypasses the app; the app's own delete_note() already
gets this for free from ProjectNote.reactions' ORM-level
cascade='all, delete-orphan'.

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
