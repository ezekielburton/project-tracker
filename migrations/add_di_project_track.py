"""
Migration: add `di_projects.track` ('internal' / 'external'), used by
DiFeature's stage_label() helper (models.py) to decide whether a board's
'management_review' stage reads as 'Management Review' or 'Client Review'
everywhere a stage label is shown.

Every existing board predates the internal/external distinction and was,
in practice, internal work — so existing rows backfill to 'internal',
matching the column's own default and changing no board's displayed
labels until someone explicitly marks it external.

Safe to re-run: checks the column first and skips the ADD (and the
backfill, which only ever targets NULL rows) if it already exists.

The pytest suite runs against its OWN separate database (TEST_DATABASE_URL,
see TestingConfig) - its schema comes from db.create_all() at test-session
start, which only creates tables that don't exist yet, so it never picks up
a new column added to an already-existing table. This script has to be run
against that database too, with --test, or the test suite keeps seeing
di_projects without a track column.

Run once against the dev/prod database: python migrations/add_di_project_track.py
Run once against the test database:     python migrations/add_di_project_track.py --test
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from config import TestingConfig

config = TestingConfig if '--test' in sys.argv else None
app = create_app(config) if config else create_app()
target = 'TEST database' if config else 'dev/prod database'
print(f"Targeting the {target}: {app.config['SQLALCHEMY_DATABASE_URI']}")

with app.app_context():
    conn = db.engine.raw_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'di_projects' AND column_name = 'track'"
    )
    already_present = cur.fetchone() is not None

    if already_present:
        print("di_projects.track already exists - skipping.")
    else:
        cur.execute(
            "ALTER TABLE di_projects ADD COLUMN track VARCHAR(10) "
            "NOT NULL DEFAULT 'internal';"
        )
        print("Added di_projects.track (default 'internal').")

    conn.commit()
    cur.close()
    conn.close()
    print("Done - di_projects.track applied.")
