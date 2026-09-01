"""
Migration: split each Digital Innovation step's single `label` field into
a short `title` (what a feature's board card shows at a glance) and an
optional longer `details` field — for both di_feature_steps (a feature's
actual steps) and di_step_templates (the per-stage defaults new steps are
seeded from).

Existing `label` values already read like short titles ("Data model",
"Draft the brief"), so renaming the column to `title` keeps every card
and checklist showing exactly what it shows today, with no behaviour
change. `details` starts empty (NULL) on every existing row — there's
nothing to migrate into it, it's a brand-new field to fill in going
forward.

Safe to re-run: checks each table's columns first and skips the rename
if `title` already exists (or if `label` is already gone).

The pytest suite runs against its OWN separate database (TEST_DATABASE_URL,
see TestingConfig) — its schema comes from db.create_all() at test-session
start, which only creates tables that don't exist yet, so it never picks up
a rename/new-column change made to an already-existing table. This script
has to be run against that database too, with --test, or the test suite
keeps seeing the old `label` column.

Run once against the dev/prod database: python migrations/add_step_title_details.py
Run once against the test database:     python migrations/add_step_title_details.py --test
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

    for table in ('di_feature_steps', 'di_step_templates'):
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND column_name IN ('label', 'title')",
            (table,),
        )
        existing = {row[0] for row in cur.fetchall()}

        if 'title' in existing:
            print(f"{table}.title already exists — skipping rename.")
        elif 'label' in existing:
            cur.execute(f"ALTER TABLE {table} RENAME COLUMN label TO title;")
            print(f"Renamed {table}.label -> {table}.title")
        else:
            print(f"{table} has neither label nor title — skipping (unexpected, check manually).")

        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS details TEXT;")
        print(f"Ensured {table}.details exists.")

    conn.commit()
    cur.close()
    conn.close()
    print("Done — title/details split applied.")
