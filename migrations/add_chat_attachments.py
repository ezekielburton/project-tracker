"""
Migration: add image/video attachment columns to project_notes (M10 chat
redesign — Phase 3, 21 Aug 2026).

attachment_filename: the UUID-based name the file is actually stored
under on the NAS (see app.nas.build_chat_file_path) — not the original
filename, since many different senders' "IMG_1234.jpg" all land in the
SAME shared per-project chat folder and would otherwise collide.

attachment_original_filename: what the sender's device called it, kept
only for display/download-name purposes.

attachment_type: 'image' | 'video' | NULL — NULL for an ordinary
text-only note, same as every note before this migration.

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
            ADD COLUMN IF NOT EXISTS attachment_filename VARCHAR(255);
        """))
        conn.execute(text("""
            ALTER TABLE project_notes
            ADD COLUMN IF NOT EXISTS attachment_original_filename VARCHAR(255);
        """))
        conn.execute(text("""
            ALTER TABLE project_notes
            ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(10);
        """))
        conn.commit()

    print("Migration complete: attachment_filename, attachment_original_filename, "
          "attachment_type added to project_notes.")
