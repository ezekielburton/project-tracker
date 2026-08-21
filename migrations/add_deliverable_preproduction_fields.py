"""
Migration: add per-deliverable pre-production fields to deliverables table.
needs_technical / needs_artwork: flags the Project Owner sets when reviewing
  a client-approved deliverable, choosing which work streams it needs.
technical_status / artwork_status: each stream's own progress, independent
  of the deliverable's design-phase status column — this is what makes
  staggered per-deliverable pre-production free (one record, two status
  layers), per Projects Redesign Architecture.md §5.
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
            ALTER TABLE deliverables
            ADD COLUMN IF NOT EXISTS needs_technical BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.execute(text("""
            ALTER TABLE deliverables
            ADD COLUMN IF NOT EXISTS needs_artwork BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.execute(text("""
            ALTER TABLE deliverables
            ADD COLUMN IF NOT EXISTS technical_status VARCHAR(50);
        """))
        conn.execute(text("""
            ALTER TABLE deliverables
            ADD COLUMN IF NOT EXISTS artwork_status VARCHAR(50);
        """))
        conn.commit()

    print("Migration complete: pre-production fields added to deliverables.")