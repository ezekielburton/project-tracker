"""Templates, autosave drafts, and save-and-publish as one action."""
import json

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as
from app.modules.wiki.lib.article_templates import ARTICLE_TEMPLATES, template_document
from app.modules.wiki.lib.blocks import is_editorjs, sanitize_document


def _admin(app, client, db_session, email):
    user = User(name='admin', email=email, role='admin')
    user.set_password('pw123456')
    db_session.add(user)
    db_session.commit()
    login_as(client, app, user, 'pw123456')
    return user


def _section(db_session, slug):
    section = WikiSection(title='S', slug=slug)
    db_session.add(section)
    db_session.commit()
    return section


def _document(blocks):
    return {'time': 0, 'version': '2.30.7', 'blocks': blocks}


def _paragraph(text):
    return {'id': 'a', 'type': 'paragraph', 'data': {'text': text}}


# ------ Templates ------

def test_every_template_is_a_valid_document():
    for template in ARTICLE_TEMPLATES:
        assert is_editorjs(template['document'])
        assert sanitize_document(template['document']) is not None


def test_templates_survive_the_save_cleaner():
    """A skeleton must not lose blocks the moment it is saved."""
    for template in ARTICLE_TEMPLATES:
        cleaned = sanitize_document(template['document'])
        assert len(cleaned['blocks']) == len(template['document']['blocks']), template['key']


def test_blank_template_is_empty():
    assert template_document('blank')['blocks'] == []


def test_unknown_template_key_is_empty_not_an_error():
    assert template_document('nope')['blocks'] == []


# ------ Autosave ------

def test_autosave_creates_a_draft_article(app, client, db_session):
    _admin(app, client, db_session, 'autosave-new@example.com')
    section = _section(db_session, 's-autosave-new')

    resp = client.post('/wiki/editor/article/autosave', data={
        'section_id': str(section.id),
        'title': 'Fresh article',
        'sections_json': json.dumps(_document([_paragraph('Some words')])),
    })

    assert resp.status_code == 200
    article = WikiArticle.query.get(resp.get_json()['article_id'])
    assert article.is_published is False
    assert 'Some words' in article.draft_sections_json
    assert json.loads(article.sections_json)['blocks'] == []


def test_autosave_without_a_title_creates_nothing(app, client, db_session):
    _admin(app, client, db_session, 'autosave-empty@example.com')
    section = _section(db_session, 's-autosave-empty')

    resp = client.post('/wiki/editor/article/autosave', data={
        'section_id': str(section.id),
        'title': '',
        'sections_json': json.dumps(_document([_paragraph('Some words')])),
    })

    assert resp.get_json()['success'] is False
    assert WikiArticle.query.count() == 0


def test_autosave_leaves_the_live_article_alone(app, client, db_session):
    _admin(app, client, db_session, 'autosave-live@example.com')
    section = _section(db_session, 's-autosave-live')
    article = WikiArticle(section_id=section.id, title='T', slug='t-live',
                          sections_json=json.dumps(_document([_paragraph('Live text')])),
                          is_published=True)
    db_session.add(article)
    db_session.commit()
    was_updated_at = article.updated_at

    client.post('/wiki/editor/article/autosave', data={
        'article_id': str(article.id),
        'section_id': str(section.id),
        'title': 'T',
        'sections_json': json.dumps(_document([_paragraph('Draft text')])),
    })
    db_session.expire_all()

    article = WikiArticle.query.get(article.id)
    assert 'Live text' in article.sections_json
    assert 'Draft text' in article.draft_sections_json
    assert article.updated_at == was_updated_at


def test_autosave_cleans_what_it_stores(app, client, db_session):
    _admin(app, client, db_session, 'autosave-clean@example.com')
    section = _section(db_session, 's-autosave-clean')

    resp = client.post('/wiki/editor/article/autosave', data={
        'section_id': str(section.id),
        'title': 'Fresh',
        'sections_json': json.dumps(_document([_paragraph('Hi <b>you</b><script>bad()</script>')])),
    })

    article = WikiArticle.query.get(resp.get_json()['article_id'])
    assert 'script' not in article.draft_sections_json
    assert '<b>you</b>' in article.draft_sections_json


# ------ Save makes it live ------

def test_save_publishes_and_clears_the_draft(app, client, db_session):
    _admin(app, client, db_session, 'save-publish@example.com')
    section = _section(db_session, 's-save-publish')
    article = WikiArticle(section_id=section.id, title='T', slug='t-save',
                          sections_json=json.dumps(_document([_paragraph('Old')])),
                          draft_sections_json=json.dumps(_document([_paragraph('New')])),
                          is_published=False)
    db_session.add(article)
    db_session.commit()

    client.post('/wiki/editor/article/save', data={
        'article_id': str(article.id),
        'section_id': str(section.id),
        'title': 'T',
        'is_published': 'on',
        'sections_json': json.dumps(_document([_paragraph('New')])),
    })
    db_session.expire_all()

    article = WikiArticle.query.get(article.id)
    assert article.is_published is True
    assert 'New' in article.sections_json
    assert article.draft_sections_json is None


def test_save_without_the_tick_unpublishes(app, client, db_session):
    _admin(app, client, db_session, 'save-unpublish@example.com')
    section = _section(db_session, 's-save-unpublish')
    article = WikiArticle(section_id=section.id, title='T', slug='t-unpub',
                          sections_json=json.dumps(_document([_paragraph('Old')])),
                          is_published=True)
    db_session.add(article)
    db_session.commit()

    client.post('/wiki/editor/article/save', data={
        'article_id': str(article.id),
        'section_id': str(section.id),
        'title': 'T',
        'sections_json': json.dumps(_document([_paragraph('Old')])),
    })
    db_session.expire_all()

    assert WikiArticle.query.get(article.id).is_published is False


def test_save_keeps_the_original_slug(app, client, db_session):
    _admin(app, client, db_session, 'save-slug@example.com')
    section = _section(db_session, 's-save-slug')
    article = WikiArticle(section_id=section.id, title='Old title', slug='old-title',
                          sections_json=json.dumps(_document([_paragraph('Body')])))
    db_session.add(article)
    db_session.commit()

    client.post('/wiki/editor/article/save', data={
        'article_id': str(article.id),
        'section_id': str(section.id),
        'title': 'A completely different title',
        'sections_json': json.dumps(_document([_paragraph('Body')])),
    })
    db_session.expire_all()

    assert WikiArticle.query.get(article.id).slug == 'old-title'

    

# ------ Moving a key says so ------

def test_moving_a_key_is_flashed(app, client, db_session):
    """Taking a key off another article is silent otherwise."""
    _admin(app, client, db_session, 'flash-key@example.com')
    section = _section(db_session, 's-flash')
    first = WikiArticle(section_id=section.id, title='The old one', slug='f-first',
                        help_key='hse.registers',
                        sections_json=json.dumps(_document([_paragraph('Body')])))
    second = WikiArticle(section_id=section.id, title='The new one', slug='f-second',
                         sections_json=json.dumps(_document([_paragraph('Body')])))
    db_session.add_all([first, second])
    db_session.commit()

    resp = client.post('/wiki/editor/article/save', data={
        'article_id': str(second.id), 'section_id': str(section.id), 'title': 'The new one',
        'help_key': 'hse.registers',
        'sections_json': json.dumps(_document([_paragraph('Body')])),
    }, follow_redirects=True)

    assert b'Help key moved from &#39;The old one&#39;' in resp.data


def test_no_flash_when_no_key_moved(app, client, db_session):
    _admin(app, client, db_session, 'flash-none@example.com')
    section = _section(db_session, 's-noflash')
    article = WikiArticle(section_id=section.id, title='Only one', slug='f-only',
                          sections_json=json.dumps(_document([_paragraph('Body')])))
    db_session.add(article)
    db_session.commit()

    resp = client.post('/wiki/editor/article/save', data={
        'article_id': str(article.id), 'section_id': str(section.id), 'title': 'Only one',
        'help_key': 'hse.registers',
        'sections_json': json.dumps(_document([_paragraph('Body')])),
    }, follow_redirects=True)

    assert b'Help key moved' not in resp.data


# ------ Bad form ids ------

def test_a_non_numeric_article_id_is_a_bad_request(app, client, db_session):
    """Straight int() on form input made this a 500."""
    _admin(app, client, db_session, 'badid-article@example.com')
    section = _section(db_session, 's-badid')

    resp = client.post('/wiki/editor/article/save', data={
        'article_id': 'abc', 'section_id': str(section.id), 'title': 'T',
        'sections_json': json.dumps(_document([_paragraph('Body')])),
    })

    assert resp.status_code == 400


def test_a_non_numeric_section_id_is_a_bad_request(app, client, db_session):
    _admin(app, client, db_session, 'badid-section@example.com')

    resp = client.post('/wiki/editor/article/create', data={
        'section_id': 'oops', 'title': 'T', 'template': 'blank',
    })

    assert resp.status_code == 400
