"""The article editor: its template contract, pinned libraries, and cleaning on save."""
import json
import os
import re

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITOR_JS = os.path.join(MODULE_DIR, 'static', 'js', 'wiki_editor.js')
EDITOR_TEMPLATE = os.path.join(MODULE_DIR, 'templates', 'wiki', 'editor_article.html')

PINNED_LIBRARIES = [
    '@editorjs/editorjs@2.30.7/dist/editorjs.umd.js',
    '@editorjs/header@2.8.9/dist/header.umd.js',
    '@editorjs/list@1.9.0/dist/list.umd.js',
    '@editorjs/image@2.10.3/dist/image.umd.js',
]


def _declared_ids():
    """Read the id list wiki_editor.js declares, rather than restating it here."""
    source = open(EDITOR_JS, encoding='utf-8').read()
    match = re.search(r'var TEMPLATE_CONTRACT = \[(.*?)\];', source, re.S)
    assert match, 'wiki_editor.js no longer declares TEMPLATE_CONTRACT'
    return re.findall(r"'([^']+)'", match.group(1))


def _admin(db_session, client, app, email):
    user = User(name='admin', email=email, role='admin')
    user.set_password('pw123456')
    db_session.add(user)
    db_session.commit()
    login_as(client, app, user, 'pw123456')
    return user


# ------ Declared contract between the editor script and its template ------

def test_editor_template_carries_every_declared_id():
    template = open(EDITOR_TEMPLATE, encoding='utf-8').read()
    for element_id in _declared_ids():
        assert f'id="{element_id}"' in template, (
            f'editor_article.html is missing id="{element_id}". Restore it, '
            f'or update TEMPLATE_CONTRACT in wiki_editor.js.'
        )


def test_editor_template_pins_every_library():
    template = open(EDITOR_TEMPLATE, encoding='utf-8').read()
    for library in PINNED_LIBRARIES:
        assert library in template, f'editor_article.html no longer loads {library}'


def test_editor_template_resolves(app):
    assert app.jinja_env.get_template('wiki/editor_article.html') is not None


# ------ Cleaning on save ------

def _save(client, section_id, document):
    return client.post('/wiki/editor/article/save', data={
        'section_id': str(section_id),
        'title': 'A title',
        'sections_json': json.dumps(document),
    })


def _document(blocks):
    return {'time': 0, 'version': '2.30.7', 'blocks': blocks}


def test_save_strips_scripts_from_paragraph_text(app, client, db_session):
    from app.modules.core.shared.models import WikiArticle, WikiSection

    _admin(db_session, client, app, 'editor-save@example.com')
    section = WikiSection(title='S', slug='s-clean')
    db_session.add(section)
    db_session.commit()

    _save(client, section.id, _document([
        {'id': 'a', 'type': 'paragraph', 'data': {'text': 'Hi <b>you</b><script>bad()</script>'}},
    ]))

    article = WikiArticle.query.filter_by(section_id=section.id).first()
    stored = json.loads(article.sections_json)
    assert stored['blocks'][0]['data']['text'] == 'Hi <b>you</b>'


def test_save_drops_unknown_block_types(app, client, db_session):
    from app.modules.core.shared.models import WikiArticle, WikiSection

    _admin(db_session, client, app, 'editor-unknown@example.com')
    section = WikiSection(title='S', slug='s-unknown')
    db_session.add(section)
    db_session.commit()

    _save(client, section.id, _document([
        {'id': 'a', 'type': 'quote', 'data': {'text': 'nope'}},
        {'id': 'b', 'type': 'paragraph', 'data': {'text': 'kept'}},
    ]))

    article = WikiArticle.query.filter_by(section_id=section.id).first()
    stored = json.loads(article.sections_json)
    assert [b['type'] for b in stored['blocks']] == ['paragraph']


def test_save_rejects_content_that_is_not_a_document(app, client, db_session):
    from app.modules.core.shared.models import WikiSection

    _admin(db_session, client, app, 'editor-bad@example.com')
    section = WikiSection(title='S', slug='s-bad')
    db_session.add(section)
    db_session.commit()

    resp = client.post('/wiki/editor/article/save', data={
        'section_id': str(section.id),
        'title': 'A title',
        'sections_json': '[{"type": "body"}]',
    })
    assert resp.status_code == 400


def test_save_rejects_unsafe_media_urls(app, client, db_session):
    from app.modules.core.shared.models import WikiArticle, WikiSection

    _admin(db_session, client, app, 'editor-url@example.com')
    section = WikiSection(title='S', slug='s-url')
    db_session.add(section)
    db_session.commit()

    _save(client, section.id, _document([
        {'id': 'a', 'type': 'image', 'data': {'file': {'url': 'javascript:alert(1)'}}},
        {'id': 'b', 'type': 'helixVideo', 'data': {'source': 'embed', 'url': 'javascript:alert(1)'}},
        {'id': 'c', 'type': 'helixVideo', 'data': {'source': 'embed', 'url': 'https://youtu.be/abc'}},
    ]))

    article = WikiArticle.query.filter_by(section_id=section.id).first()
    stored = json.loads(article.sections_json)
    assert len(stored['blocks']) == 1
    assert stored['blocks'][0]['data']['url'] == 'https://youtu.be/abc'


def test_svg_upload_is_rejected(app, client, db_session):
    """Same-origin svg can carry script."""
    import io as _io
    _admin(db_session, client, app, 'editor-svg@example.com')

    resp = client.post('/wiki/upload-image', data={'file': (_io.BytesIO(b'<svg/>'), 'logo.svg')})

    assert resp.status_code == 400
    assert resp.get_json()['success'] is False
