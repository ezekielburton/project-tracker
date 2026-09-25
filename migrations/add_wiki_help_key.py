"""
Migration: add help_key column to wiki_articles.
Run once: python migrations/add_wiki_help_key.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db

app = create_app()
with app.app_context():
    conn = db.engine.raw_connection()
    cur  = conn.cursor()
    cur.execute("""
        ALTER TABLE wiki_articles
        ADD COLUMN IF NOT EXISTS help_key VARCHAR(100);
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — help_key column added to wiki_articles.")
