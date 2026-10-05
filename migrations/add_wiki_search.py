"""
Migration: wiki_articles.search_text and search_vector, each article's plain
words and the weighted index Postgres builds from them and the title.
Fills search_text for every existing article without moving its updated_at.
Run via migrate.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app import create_app, db
from app.modules.core.shared.models.wiki import SEARCH_VECTOR_SQL
from app.modules.wiki.lib.blocks import document_text, is_editorjs, to_editorjs

app = create_app()
with app.app_context():
    db.session.execute(text('ALTER TABLE wiki_articles ADD COLUMN IF NOT EXISTS search_text TEXT'))
    db.session.execute(text(
        'ALTER TABLE wiki_articles ADD COLUMN IF NOT EXISTS search_vector tsvector '
        f'GENERATED ALWAYS AS ({SEARCH_VECTOR_SQL}) STORED'))
    db.session.execute(text(
        'CREATE INDEX IF NOT EXISTS ix_wiki_articles_search_vector '
        'ON wiki_articles USING gin (search_vector)'))

    rows = db.session.execute(text('SELECT id, sections_json FROM wiki_articles')).all()
    for row in rows:
        try:
            parsed = json.loads(row.sections_json or '{}')
        except ValueError:
            parsed = {}
        document = parsed if is_editorjs(parsed) else to_editorjs(parsed if isinstance(parsed, list) else [])
        # Raw SQL, so the ORM's onupdate leaves each article's Last updated date alone.
        db.session.execute(text('UPDATE wiki_articles SET search_text = :words WHERE id = :id'),
                           {'words': document_text(document), 'id': row.id})
    db.session.commit()
    print(f'Done: search columns added, {len(rows)} article(s) indexed.')
