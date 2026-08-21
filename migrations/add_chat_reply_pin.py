"""
Migration: add reply-to and pin support to project_notes (M10 chat
redesign — WhatsApp-style message interactions, 21 Aug 2026).

reply_to_id: self-referential FK — set when a message was sent as a
reply, so the chat drawer can render the quoted snippet above the new
bubble the way WhatsApp does. ON DELETE SET NULL rather than CASCADE:
deleting the original message a reply pointed to should orphan the
reply's quote (it just stops rendering a snippet), not delete the reply
itself.

is_pinned: one or more messages per project can be pinned to the top of
the thread via the new per-message chevron menu's "Pin" action.

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
            ALTER TABLE project_notes
            ADD COLUMN IF NOT EXISTS reply_to_id INTEGER REFERENCES project_notes(id) ON DELETE SET NULL;
        """))
        conn.execute(text("""
            ALTER TABLE project_notes
            ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.commit()

    print("Migration complete: reply_to_id, is_pinned added to project_notes.")
