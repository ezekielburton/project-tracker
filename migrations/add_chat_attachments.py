"""Migration: add image/video attachment columns to project_notes
(filename, original_filename, type). Run via migrate.py."""
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
