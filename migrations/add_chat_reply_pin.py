"""Migration: add reply-to (self-referential FK, SET NULL on delete) and
is_pinned columns to project_notes. Run via migrate.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE project_notes
            ADD COLUMN IF NOT EXISTS reply_to_id INTEGER REFERENCES project_notes(id) ON DELETE SET NULL;
        """))
        conn.execute(text("""
            ALTER TABLE project_notes
            ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.commit()

    print("Migration complete: reply_to_id, is_pinned added to project_notes.")
