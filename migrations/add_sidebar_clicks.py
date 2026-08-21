"""
Migration: create sidebar_clicks table.
Tracks which sidebar links are clicked for admin usage analytics.
Run once from the project root: python add_sidebar_clicks.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sidebar_clicks (
                id SERIAL PRIMARY KEY,
                link_name VARCHAR(100) NOT NULL,
                user_id INTEGER,
                user_role VARCHAR(50),
                clicked_at TIMESTAMP NOT NULL DEFAULT NOW()
                          
            );
        """))
        conn.commit()
    
    print("Migration complete: sidebar_clicks table created.")