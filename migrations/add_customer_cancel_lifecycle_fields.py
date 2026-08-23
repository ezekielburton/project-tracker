"""
Migration: Add Cancel lifecycle fields to project_customers table.

project_customers.cancelled (BOOLEAN) already existed, added by
add_customer_cancelled.py, but nothing ever set it — every read site
(dashboard.py, project_list.py, project_overlay.py, project_preproduction.py)
already treats a cancelled customer as excluded from active work, there was
just no write path. This adds the same reason/who/when trio
add_project_lifecycle_fields.py added at the project level, so cancelling a
customer carries the same audit trail Cancel Project already does — useful
for invoicing, since "when exactly was this customer frozen" is what
determines what's billable up to.

Cancel is reversible (Reactivate clears cancelled back to FALSE and the
other three back to NULL) — same shape as Project's Cancel/Reactivate,
just scoped to one customer within a C&CM project instead of the whole
project. There is no soft-delete equivalent here (no is_deleted/deleted_at/
deleted_by_id) — that's a separate, rarer, admin-only action at the project
level; nothing asked for it per-customer.

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
            ALTER TABLE project_customers
            ADD COLUMN IF NOT EXISTS cancel_reason TEXT;
        """))
        conn.execute(text("""
            ALTER TABLE project_customers
            ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP;
        """))
        conn.execute(text("""
            ALTER TABLE project_customers
            ADD COLUMN IF NOT EXISTS cancelled_by_id INTEGER REFERENCES users(id);
        """))
        conn.commit()

    print("Migration complete: cancel lifecycle fields added to project_customers.")
