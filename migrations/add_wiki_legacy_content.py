"""
Migration: add legacy_sections_json column to wiki_articles.
Run once: python migrations/add_wiki_legacy_content.py
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
        ADD COLUMN IF NOT EXISTS legacy_sections_json TEXT;
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("Done — legacy_sections_json column added to wiki_articles.")
