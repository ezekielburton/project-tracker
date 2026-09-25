"""The editor dashboard: drag ordering, the overlays, and creating from a skeleton."""
import json
import os
import re

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_JS = os.path.join(MODULE_DIR, 'static', 'js', 'editor_dashboard.js')
DASHBOARD_TEMPLATE = os.path.join(MODULE_DIR, 'templates', 'wiki', 'editor_dashboard.html')
SECTION_MODAL = os.path.join(MODULE_DIR, 'templates', 'wiki', '_section_modal.html')
ARTICLE_MODAL = os.path.join(MODULE_DIR, 'templates', 'wiki', '_article_modal.html')


def _declared_ids():
    """Read the id list editor_dashboard.js declares, rather than restating it here."""
    source = open(DASHBOARD_JS, encoding='utf-8').read()
    match = re.search(r'var TEMPLATE_CONTRACT = \[(.*?)\];', source, re.S)
    assert match, 'editor_dashboard.js no longer declares TEMPLATE_CONTRACT'
    return re.findall(r"'([^']+)'", match.group(1))


def _user(app, client, db_session, email, role='admin'):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password('pw123456')
    db_session.add(user)
    db_session.commit()
    login_as(client, app, user, 'pw123456')
    return user


def _section(db_session, slug, order=0, title='S'):
    section = WikiSection(title=title, slug=slug, sort_order=order)
    db_session.add(section)
    db_session.commit()
    return section


def _article(db_session, section, slug, order=0, title='A'):
    article = WikiArticle(section_id=section.id, title=title, slug=slug, sort_order=order,
                          sections_json=json.dumps({'time': 0, 'version': '2.30.7', 'blocks': []}))
    db_session.add(article)
    db_session.commit()
    return article


# ------ Declared contract between the dashboard script and its markup ------

def test_dashboard_markup_carries_every_declared_id():
    markup = ''.join(open(path, encoding='utf-8').read()
                     for path in (DASHBOARD_TEMPLATE, SECTION_MODAL, ARTICLE_MODAL))
    for element_id in _declared_ids():
        assert f'id="{element_id}"' in markup, (
            f'The dashboard markup is missing id="{element_id}". Restore it, '
            f'or update TEMPLATE_CONTRACT in editor_dashboard.js.'
        )


def test_dashboard_templates_resolve(app):
    for name in ('wiki/editor_dashboard.html', 'wiki/_section_modal.html', 'wiki/_article_modal.html'):
        assert app.jinja_env.get_template(name) is not None


# ------ Reordering ------

def test_section_reorder_writes_list_position(app, client, db_session):
    _user(app, client, db_session, 'reorder-sections@example.com')
    first = _section(db_session, 'r-one', order=0, title='One')
    second = _section(db_session, 'r-two', order=1, title='Two')

    resp = client.post('/wiki/editor/sections/reorder',
                       json={'section_ids': [second.id, first.id]})
    db_session.expire_all()

    assert resp.status_code == 200
    assert WikiSection.query.get(second.id).sort_order == 0
    assert WikiSection.query.get(first.id).sort_order == 1


def test_article_reorder_does_not_touch_updated_at(app, client, db_session):
    _user(app, client, db_session, 'reorder-articles@example.com')
    section = _section(db_session, 'r-articles')
    first = _article(db_session, section, 'a-one', order=0)
    second = _article(db_session, section, 'a-two', order=1)
    was_updated_at = first.updated_at

    client.post('/wiki/editor/articles/reorder',
                json={'article_ids': [second.id, first.id]})
    db_session.expire_all()

    assert WikiArticle.query.get(second.id).sort_order == 0
    assert WikiArticle.query.get(first.id).sort_order == 1
    assert WikiArticle.query.get(first.id).updated_at == was_updated_at


def test_reorder_is_admin_only(app, client, db_session):
    _user(app, client, db_session, 'reorder-designer@example.com', role='designer')
    resp = client.post('/wiki/editor/sections/reorder', json={'section_ids': []})
    assert resp.status_code == 403


# ------ Creating from the overlay ------

def test_create_article_seeds_the_chosen_skeleton(app, client, db_session):
    _user(app, client, db_session, 'create-howto@example.com')
    section = _section(db_session, 'c-howto')

    client.post('/wiki/editor/article/create', data={
        'section_id': str(section.id), 'title': 'Doing the thing', 'template': 'how-to',
    })

    article = WikiArticle.query.filter_by(section_id=section.id).first()
    blocks = json.loads(article.sections_json)['blocks']
    assert article.is_published is False
    assert len(blocks) > 0
    assert blocks[0]['type'] == 'header'


def test_create_article_blank_template_is_empty(app, client, db_session):
    _user(app, client, db_session, 'create-blank@example.com')
    section = _section(db_session, 'c-blank')

    client.post('/wiki/editor/article/create', data={
        'section_id': str(section.id), 'title': 'Empty one', 'template': 'blank',
    })

    article = WikiArticle.query.filter_by(section_id=section.id).first()
    assert json.loads(article.sections_json)['blocks'] == []


def test_new_article_lands_at_the_end_of_its_section(app, client, db_session):
    _user(app, client, db_session, 'create-order@example.com')
    section = _section(db_session, 'c-order')
    _article(db_session, section, 'existing', order=7)

    client.post('/wiki/editor/article/create', data={
        'section_id': str(section.id), 'title': 'Newer', 'template': 'blank',
    })

    assert WikiArticle.query.filter_by(title='Newer').first().sort_order == 8


# ------ Section overlay save ------

def test_section_save_sets_publish_state_and_roles(app, client, db_session):
    _user(app, client, db_session, 'section-save@example.com')

    client.post('/wiki/editor/section/save', data={
        'title': 'Client Servicing', 'is_published': 'on', 'relevant_roles': ['CS', 'Management'],
    })

    section = WikiSection.query.filter_by(title='Client Servicing').first()
    assert section.is_published is True
    assert section.relevant_roles == 'CS,Management'
    assert section.slug == 'client-servicing'


def test_section_slug_clash_gets_a_suffix(app, client, db_session):
    _user(app, client, db_session, 'section-clash@example.com')
    _section(db_session, 'projects', title='Projects')

    client.post('/wiki/editor/section/save', data={'title': 'Projects'})

    slugs = sorted(s.slug for s in WikiSection.query.all())
    assert slugs == ['projects', 'projects-2']


def test_section_edit_keeps_its_slug(app, client, db_session):
    _user(app, client, db_session, 'section-slug@example.com')
    section = _section(db_session, 'original-slug', title='Original')

    client.post('/wiki/editor/section/save', data={
        'section_id': str(section.id), 'title': 'Renamed entirely',
    })
    db_session.expire_all()

    assert WikiSection.query.get(section.id).slug == 'original-slug'
