"""
Migration: index activity_logs(entity_type, entity_id) and
project_notes(project_id).

Why (27 Aug 2026, per Ezekiel — "project page hanging, especially on
filters or closing an overlay, 30s+"): the unread-dots feature
(_bulk_activity_and_chat_at() in project_list.py) added a query that runs
on EVERY /projects-new page load, EVERY filter/sort action, and every SSE-
triggered live refresh (including the one that fires when an overlay
closes, since project_overlay/project_notes edits touch watched models):

    SELECT entity_id, MAX(created_at) FROM activity_logs
    WHERE entity_type = 'project' AND entity_id IN (...)
    GROUP BY entity_id

activity_logs is an app-wide audit log — every log_activity() call site in
the whole app writes to it, not just projects — so it grows continuously
and had no index on entity_type/entity_id at all. Without one, that query
(and the matching project_notes.project_id one, for the chat-unread half
of the same feature) is a full sequential scan every single time, which
is exactly the "hangs on filters / closing an overlay" symptom: both
paths funnel through project_list.py's one _fetch_all_view_rows()
choke point, which calls _bulk_activity_and_chat_at() unconditionally.

CONCURRENTLY so this doesn't take a write lock on either table while it
runs — this is a live system, not a maintenance window. CONCURRENTLY
cannot run inside a transaction block, hence conn.autocommit = True below
(a plain "BEGIN; CREATE INDEX CONCURRENTLY; COMMIT;" is a Postgres error).

Run via: python migrate.py (NOT directly - see migrate.py at project root)
IF NOT EXISTS makes re-running this harmless.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_activity_logs_entity_type_entity_id
        ON activity_logs (entity_type, entity_id);
    """)
    cur.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_project_notes_project_id
        ON project_notes (project_id);
    """)

    cur.close()
    conn.close()
    print("Done - added activity_logs(entity_type, entity_id) and project_notes(project_id) indexes.")
