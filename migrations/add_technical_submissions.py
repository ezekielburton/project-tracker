"""
Migration: add technical submission tracking
Run once via:  python migrate.py   (do NOT run this file directly — migrate.py
records it in the schema_migrations table so it never runs twice)

This migration supports the new "Technical" tab: a parallel submission track
for technical deliverables (drawings/CAD files) that has its own internal
review cycle, completely separate from the existing design-tab submission
flow (ProjectSubmission) and from project.project_status.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app import create_app, db

app = create_app()
with app.app_context():
    # --- Column 1: technical_revision_count on deliverables -----------------
    # Mirrors the existing `revision_count` column Deliverable already has for
    # the design-tab flow, but tracked independently for the technical flow.
    # Starts at 0 for every deliverable (including ones that already exist)
    # and is incremented by the "flag" route each time CS sends a technical
    # file back for rework. The upload route reads this value to decide
    # whether the next auto-generated filename should say "Initial" (count
    # is still 0) or "Revision {count}" (count is 1+).
    db.session.execute(text("""
        ALTER TABLE deliverables
        ADD COLUMN IF NOT EXISTS technical_revision_count INTEGER NOT NULL DEFAULT 0;
    """))

    # --- Table: technical_submissions ---------------------------------------
    # One row per uploaded technical file. A deliverable can accumulate many
    # rows over time (initial upload, then a new row each revision) — the
    # "latest row for this deliverable" is what the Technical Drawings card
    # shows as the current state; older rows form the collapsible history.
    #
    # ON DELETE CASCADE on project_id/deliverable_id means deleting a project
    # or one of its deliverables automatically cleans up any technical
    # submissions attached to it — no orphaned rows left behind, same
    # cascade behavior used by project_submission_files above.
    db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS technical_submissions (
            id SERIAL PRIMARY KEY,

            -- Which project and deliverable this file belongs to. Both are
            -- stored (not just deliverable_id) so queries that need "every
            -- technical submission for this project" don't have to join
            -- through deliverables first.
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            deliverable_id INTEGER NOT NULL REFERENCES deliverables(id) ON DELETE CASCADE,

            -- The auto-generated filename (e.g. "Technical Drawing - Acme
            -- Rebrand - Initial.pdf") and its extension, same shape as
            -- ProjectSubmission's original_filename/file_type pair.
            original_filename VARCHAR(500) NOT NULL,
            file_type VARCHAR(10) NOT NULL,

            -- Who uploaded this file and when.
            uploaded_by_id INTEGER NOT NULL REFERENCES users(id),
            uploaded_at TIMESTAMP DEFAULT NOW(),

            -- Lifecycle state. Starts 'uploaded' the moment the file lands
            -- on the NAS, moves to 'internal_review' once the designer/team
            -- lead explicitly submits it, then ends at either
            -- 'internal_revision' (CS flagged it — back to the designer) or
            -- 'internally_approved' (terminal state, CS/admin/management
            -- signed off). This status is entirely independent of
            -- project.project_status and of ProjectSubmission's own status.
            status VARCHAR(50) NOT NULL DEFAULT 'uploaded',

            -- Populated only when status = 'internal_revision': what CS
            -- said was wrong, and who/when they said it. Cleared/unused
            -- otherwise (a fresh upload starts with these all NULL).
            flag_message TEXT,
            flagged_by_id INTEGER REFERENCES users(id),
            flagged_at TIMESTAMP,

            -- Populated only when status = 'internally_approved': who
            -- approved it and when. This is the terminal state for this
            -- track — nothing currently transitions a row out of it.
            internally_approved_at TIMESTAMP,
            internally_approved_by_id INTEGER REFERENCES users(id)
        );
    """))

    db.session.commit()
    print("Done — technical_revision_count column and technical_submissions table created.")
