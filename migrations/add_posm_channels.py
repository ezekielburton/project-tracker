"""
Migration: create project_posm_channels table.
Each row is one parallel POSM submission channel (UAE per customer, others per country).
Run once from the project root:  python add_posm_channels.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_posm_channels (
                id SERIAL PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                posm_country VARCHAR(50) NOT NULL,
                posm_customer_id INTEGER REFERENCES project_customers(id) ON DELETE SET NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'in_queue',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """))
        conn.commit()

    print("Migration complete: project_posm_channels table created.")
