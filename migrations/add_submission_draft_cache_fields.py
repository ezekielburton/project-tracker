"""
Migration: add Submissions Draft-cache fields (M3 Step 4).

storage_location / local_cache_path (project_submission_files): support the
new Draft-stage caching model. While a submission is in Draft, uploaded files
sit in a local cache folder (storage_location='cache', local_cache_path
pointing at the cached file) rather than going straight to the NAS. At Submit
to Client, every cached file for that submission is zipped into one archive
and uploaded to the NAS as a single object; those rows then flip to
storage_location='nas' (local_cache_path cleared). Files attached via the
existing "Attach Supporting File" flow (after a submission has already left
Draft) are unaffected — they keep going straight to NAS as storage_location=
'nas' from the moment they're uploaded, same as every row that exists today.

is_main_deck (project_submission_files): exactly one file per active draft
can be flagged as the main deck. Auto-set when a draft holds exactly one
file; the designer can switch it explicitly once more than one file exists.
At zip-build time the main-deck file gets the canonical auto-generated name
(its own extension) as its entry inside the zip; every other file keeps its
own uploaded name.

post_approval_edit_count (project_submissions): tracks how many times an
already-Client-Approved submission's file has been edited/replaced post-
approval — a separate concept from a real revision (which reopens formal
review). Stored as a plain counter, matching this codebase's existing
revision_count / posm_revision_count / ckv_revision_count pattern rather
than deriving it from activity logs (log_activity() doesn't support
structured diffs yet — that's M4 scope).

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
            ALTER TABLE project_submission_files
            ADD COLUMN IF NOT EXISTS storage_location VARCHAR(10) NOT NULL DEFAULT 'nas';
        """))
        conn.execute(text("""
            ALTER TABLE project_submission_files
            ADD COLUMN IF NOT EXISTS local_cache_path VARCHAR(500);
        """))
        conn.execute(text("""
            ALTER TABLE project_submission_files
            ADD COLUMN IF NOT EXISTS is_main_deck BOOLEAN NOT NULL DEFAULT FALSE;
        """))
        conn.execute(text("""
            ALTER TABLE project_submissions
            ADD COLUMN IF NOT EXISTS post_approval_edit_count INTEGER NOT NULL DEFAULT 0;
        """))
        conn.commit()

    print("Migration complete: storage_location, local_cache_path, is_main_deck added to "
          "project_submission_files; post_approval_edit_count added to project_submissions.")