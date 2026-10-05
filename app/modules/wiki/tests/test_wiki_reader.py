"""The reader on the shared rail: article pages, who may open them, and what sits beside them."""
import json
import os
import re
from datetime import datetime, timedelta

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as

PW = 'pw123456'
WIKI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER_JS = os.path.join(WIKI_DIR, 'static', 'js', 'wiki_reader.js')
READER_TEMPLATES = ('index.html', 'article.html', 'search.html')
CLOSED = 'module-rail-children--closed'


def test_reader_pages_require_login(client):
    for url in ('/wiki', '/wiki/article/1', '/wiki/search'):
        assert client.get(url).status_code in (302, 401), url


def _declared_ids():
    """Read the id list wiki_reader.js declares, rather than restating it here."""
    match = re.search(r'var TEMPLATE_CONTRACT = \[(.*?)\];', open(READER_JS, encoding='utf-8').read(), re.S)
    assert match, 'wiki_reader.js no longer declares TEMPLATE_CONTRACT'
    return re.findall(r"'([^']+)'", match.group(1))


def test_reader_templates_carry_every_declared_id():
    for name in READER_TEMPLATES:
        template = open(os.path.join(WIKI_DIR, 'templates', 'wiki', name), encoding='utf-8').read()
        assert 'wiki_reader.js' in template, f'{name} no longer loads wiki_reader.js'
        for element_id in _declared_ids():
            assert f'id="{element_id}"' in template, (
                f'{name} is missing id="{element_id}". Restore it, '
                f'or update TEMPLATE_CONTRACT in wiki_reader.js.')


def _user(db_session, email, role):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password(PW)
    db_session.add(user)
    db_session.commit()
    return user


def _client(app, user, emulating=None):
    """Log in just before use: requests share the test's app context, so the
    latest login is who every request runs as."""
    client = app.test_client()
    login_as(client, app, user, PW)
    if emulating is not None:
        with client.session_transaction() as sess:
            sess['emulating_user_id'] = emulating.id
    return client


def _section(db_session, slug, roles=None, order=0):
    section = WikiSection(title=slug, slug=slug, relevant_roles=roles, is_published=True,
                          sort_order=order)
    db_session.add(section)
    db_session.commit()
    return section


def _article(db_session, section, title, blocks=None, published=True, order=0, **fields):
    document = {'time': 0, 'version': '2.30.7', 'blocks': blocks or []}
    article = WikiArticle(section_id=section.id, title=title, slug=title.lower().replace(' ', '-'),
                          sections_json=json.dumps(document), is_published=published, sort_order=order,
                          **fields)
    db_session.add(article)
    db_session.commit()
    return article


# ------ The article page ------

def test_an_article_is_its_own_page_on_the_rail(app, db_session):
    section = _section(db_session, 'read-page')
    article = _article(db_session, section, 'Reading page')

    body = _client(app, _user(db_session, 'read-page@example.com', 'designer')) \
        .get(f'/wiki/article/{article.id}').get_data(as_text=True)

    assert 'class="module-rail"' in body or 'module-rail"' in body
    assert '<h1>Reading page</h1>' in body
    assert 'module-rail-subitem--active' in body


def test_a_draft_is_refused_to_readers_and_to_an_emulating_admin(app, db_session):
    section = _section(db_session, 'read-draft')
    draft = _article(db_session, section, 'Hidden draft', published=False)
    designer = _user(db_session, 'read-draft-designer@example.com', 'designer')
    admin = _user(db_session, 'read-draft-admin@example.com', 'admin')

    assert _client(app, designer).get(f'/wiki/article/{draft.id}').status_code == 403
    assert _client(app, admin, emulating=designer).get(f'/wiki/article/{draft.id}').status_code == 403
    body = _client(app, admin).get(f'/wiki/article/{draft.id}').get_data(as_text=True)
    assert 'wiki-draft-badge' in body


def test_on_this_page_links_to_each_heading(app, db_session):
    section = _section(db_session, 'read-toc')
    article = _article(db_session, section, 'With headings', blocks=[
        {'id': 'h1', 'type': 'header', 'data': {'text': 'Before you start', 'level': 3}},
        {'id': 'p1', 'type': 'paragraph', 'data': {'text': 'Words'}},
        {'id': 'h2', 'type': 'header', 'data': {'text': 'Steps', 'level': 3}},
    ])

    body = _client(app, _user(db_session, 'read-toc@example.com', 'designer')) \
        .get(f'/wiki/article/{article.id}').get_data(as_text=True)

    for index, text in ((1, 'Before you start'), (3, 'Steps')):
        assert f'id="wiki-h-{index}"' in body
        assert f'<a href="#wiki-h-{index}">{text}</a>' in body


def test_related_lists_up_to_three_others_from_the_section(app, db_session):
    section = _section(db_session, 'read-related')
    articles = [_article(db_session, section, f'Sibling {i}', order=i) for i in range(5)]

    body = _client(app, _user(db_session, 'read-related@example.com', 'designer')) \
        .get(f'/wiki/article/{articles[0].id}').get_data(as_text=True)
    related = body[body.index('>Related<'):]

    assert [f'Sibling {i}' in related for i in range(5)] == [False, True, True, True, False]


# ------ The rail ------

def test_the_open_articles_section_is_open_even_for_another_role(app, db_session):
    section = _section(db_session, 'read-cs', roles='cs')
    article = _article(db_session, section, 'CS only page')

    body = _client(app, _user(db_session, 'read-open@example.com', 'designer')) \
        .get(f'/wiki/article/{article.id}').get_data(as_text=True)

    assert CLOSED not in body


def test_sections_with_nothing_to_read_are_left_off_the_rail(app, db_session):
    _section(db_session, 'read-empty-section')
    body = _client(app, _user(db_session, 'read-empty@example.com', 'designer')).get('/wiki').get_data(as_text=True)
    assert 'read-empty-section' not in body


# ------ Links into the reader ------

def test_the_help_tray_opens_the_article_page(app, db_session):
    section = _section(db_session, 'read-tray')
    article = _article(db_session, section, 'Tray page')

    body = _client(app, _user(db_session, 'read-tray@example.com', 'designer')) \
        .get(f'/wiki/help/article/{article.id}').get_data(as_text=True)

    assert f'href="/wiki/article/{article.id}"' in body


def test_the_home_page_can_forward_old_hash_links(app, db_session):
    body = _client(app, _user(db_session, 'read-legacy@example.com', 'designer')).get('/wiki').get_data(as_text=True)
    assert 'data-article-url="/wiki/article/"' in body


# ------ The home page ------

def _home_rows(db_session):
    """Getting started for everyone, then a designer section and a CS section, four articles each."""
    for position, (slug, roles) in enumerate((('home-start', None), ('home-design', 'designer'),
                                              ('home-cs', 'cs'))):
        section = _section(db_session, slug, roles=roles, order=position)
        for i in range(4):
            _article(db_session, section, f'{slug} {i}', order=i)


def _start_titles(body):
    start = body[body.index('class="wiki-start"'):]
    return re.findall(r'class="wiki-start__title">([^<]+)<', start[:start.index('</ol>')])


def _recent_titles(body):
    return re.findall(r'class="wiki-recent__row">\s*<a [^>]*>([^<]+)</a>', body)


def test_start_here_takes_getting_started_then_the_readers_role(app, db_session):
    _home_rows(db_session)
    body = _client(app, _user(db_session, 'home-designer@example.com', 'designer')).get('/wiki').get_data(as_text=True)

    assert _start_titles(body) == ['home-start 0', 'home-start 1', 'home-start 2',
                                   'home-design 0', 'home-design 1', 'home-design 2']


def test_a_role_with_no_section_gets_only_getting_started(app, db_session):
    _home_rows(db_session)
    body = _client(app, _user(db_session, 'home-finance@example.com', 'finance')).get('/wiki').get_data(as_text=True)

    assert _start_titles(body) == ['home-start 0', 'home-start 1', 'home-start 2']


def test_an_admin_emulating_a_designer_gets_the_designers_path(app, db_session):
    _home_rows(db_session)
    admin = _user(db_session, 'home-emu-admin@example.com', 'admin')
    designer = _user(db_session, 'home-emu-designer@example.com', 'designer')

    body = _client(app, admin, emulating=designer).get('/wiki').get_data(as_text=True)

    assert _start_titles(body)[3:] == ['home-design 0', 'home-design 1', 'home-design 2']


def test_readers_never_see_drafts_on_the_home_page(app, db_session):
    section = _section(db_session, 'home-drafts')
    _article(db_session, section, 'Secret draft', published=False, order=0)
    _article(db_session, section, 'Public page', order=1,
             updated_at=datetime.utcnow() - timedelta(days=3))

    body = _client(app, _user(db_session, 'home-drafts@example.com', 'designer')).get('/wiki').get_data(as_text=True)

    assert 'Secret draft' not in body
    assert _start_titles(body) == ['Public page']
    assert _recent_titles(body) == ['Public page']


def test_recently_updated_is_newest_first_and_capped(app, db_session):
    section = _section(db_session, 'home-recent')
    for age in range(7):
        _article(db_session, section, f'Aged {age}', order=age,
                 updated_at=datetime.utcnow() - timedelta(days=age))

    body = _client(app, _user(db_session, 'home-recent@example.com', 'designer')).get('/wiki').get_data(as_text=True)

    assert _recent_titles(body) == [f'Aged {age}' for age in range(5)]


def test_an_empty_wiki_draws_no_panels(app, db_session):
    body = _client(app, _user(db_session, 'home-empty@example.com', 'designer')).get('/wiki').get_data(as_text=True)

    assert 'class="wiki-start"' not in body
    assert 'class="wiki-recent"' not in body
