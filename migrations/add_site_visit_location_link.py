"""Migration: add location_link column to site_visits (optional maps/
address URL, separate from the location name). Run via migrate.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE site_visits
            ADD COLUMN IF NOT EXISTS location_link VARCHAR(500);
        """))
        conn.commit()

    print("Migration complete: location_link added to site_visits.")
