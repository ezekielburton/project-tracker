"""
Migration: add autosave draft columns to wiki_articles.
Run once: python migrations/add_wiki_draft_content.py
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
        ADD COLUMN IF NOT EXISTS draft_sections_json TEXT,
        ADD COLUMN IF NOT EXISTS draft_saved_at TIMESTAMP;
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — draft columns added to wiki_articles.")
