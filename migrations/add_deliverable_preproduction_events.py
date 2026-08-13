"""
Migration: add deliverable_preproduction_events (M8 groundwork — backend
built ahead of the Figma-gated Pre-Production tab, 13 Aug 2026).

Append-only log for Project Owner flags on a deliverable's technical/
artwork release stream ("bounced back for reupload, here's why"). Its own
table rather than reusing ProjectSubmissionEvent — pre-production isn't
submission-scoped (a deliverable can arrive here via Skip to Pre-
Production with no submission involved), and Ezekiel wants this history
kept separate from Submissions' own log rather than filtered out of a
shared one. event_type is 'preprod_flag' for now — its own value so later
KPI queries (average revision rounds, per project/deliverable/owner/month/
quarter) can filter cleanly. stream ('technical'/'artwork') lets those same
KPIs break down by which release stream was flagged.

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
            CREATE TABLE IF NOT EXISTS deliverable_preproduction_events (
                id SERIAL PRIMARY KEY,
                deliverable_id INTEGER NOT NULL REFERENCES deliverables(id),
                event_type VARCHAR(30) NOT NULL,
                stream VARCHAR(20),
                author_id INTEGER NOT NULL REFERENCES users(id),
                message TEXT,
                created_at TIMESTAMP
            );
        """))
        conn.commit()

    print("Migration complete: deliverable_preproduction_events table created.")
