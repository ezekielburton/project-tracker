"""Add concept_approved_at and concept_approved_by_id to the projects table."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

from app import create_app, db

app = create_app()
with app.app_context():
    with db.engine.connect() as conn:
        cur = conn.connection.cursor()
        cur.execute("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS concept_approved_at TIMESTAMP WITHOUT TIME ZONE,
            ADD COLUMN IF NOT EXISTS concept_approved_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
        """)
        conn.connection.commit()
        print("Done — concept_approved_at and concept_approved_by_id added to projects.")
