"""
Migration: convert wiki article content from the old block array to the
Editor.js document shape, keeping the original in legacy_sections_json.
Dry run: python migrations/migrate_wiki_to_editorjs.py
Apply:   python migrations/migrate_wiki_to_editorjs.py --confirm
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app import create_app, db
from app.modules.wiki.lib.blocks import to_editorjs, is_editorjs

CONFIRM = '--confirm' in sys.argv

# Raw SQL so the ORM's onupdate does not rewrite every article's updated_at.
_UPDATE = text("""
    UPDATE wiki_articles
    SET sections_json = :content,
        legacy_sections_json = COALESCE(legacy_sections_json, :legacy)
    WHERE id = :id
""")

app = create_app()
with app.app_context():
    rows = db.session.execute(
        text('SELECT id, title, sections_json FROM wiki_articles ORDER BY id')
    ).all()

    converted = skipped = unreadable = 0

    for row in rows:
        try:
            parsed = json.loads(row.sections_json or '[]')
        except ValueError:
            unreadable += 1
            print(f'  ! {row.id} "{row.title}" — unreadable content, left alone')
            continue

        if is_editorjs(parsed):
            skipped += 1
            continue

        old_blocks = parsed if isinstance(parsed, list) else []
        document = to_editorjs(old_blocks)
        converted += 1
        print(f'  - {row.id} "{row.title}": {len(old_blocks)} old block(s) -> {len(document["blocks"])} new')

        if CONFIRM:
            db.session.execute(_UPDATE, {
                'id': row.id,
                'content': json.dumps(document),
                'legacy': row.sections_json,
            })

    if CONFIRM:
        db.session.commit()
        print(f'Done — {converted} converted, {skipped} already converted, {unreadable} unreadable.')
    else:
        print(f'Dry run — {converted} would convert, {skipped} already converted, {unreadable} unreadable.')
        print('Re-run with --confirm to apply.')
