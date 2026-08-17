"""
Migration: split the combined artwork stream into independent 2D and 3D
streams on the deliverables table.

Design (locked with Ezekiel, 17 Aug 2026): Pre-Production previously
collapsed 2D+3D into one needs_artwork/artwork_status pair. Design already
treats 2D/3D/Technical as three fully independent teams (a deliverable can
need all three, each with its own assignee) — Pre-Production now matches
that: each of 2D/3D/Technical gets its own needs_*/status_* pair, its own
assignment, its own mark-done/approve/flag cycle.

needs_technical/technical_status are untouched (Technical was already its
own stream). needs_artwork/artwork_status are left in place, unused going
forward — additive migration, no drops, no data loss, per the standing
migration approach.
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
            ADD COLUMN IF NOT EXISTS needs_2d BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.execute(text("""
            ALTER TABLE deliverables
            ADD COLUMN IF NOT EXISTS needs_3d BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.execute(text("""
            ALTER TABLE deliverables
            ADD COLUMN IF NOT EXISTS status_2d VARCHAR(50);
        """))
        conn.execute(text("""
            ALTER TABLE deliverables
            ADD COLUMN IF NOT EXISTS status_3d VARCHAR(50);
        """))
        conn.commit()

    print("Migration complete: needs_2d/status_2d/needs_3d/status_3d added to deliverables.")