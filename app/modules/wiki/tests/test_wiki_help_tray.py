"""The contextual "?" — its routes, what a non-admin sees, and the dock pill."""
import json
import os

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TRAY_DOCK = os.path.join(APP_DIR, 'modules', 'core', 'shared', 'templates', 'partials', 'tray_dock.html')
SHARED_MACROS = os.path.join(APP_DIR, 'modules', 'core', 'shared', 'templates', '_shared_macros.html')
BASE_TEMPLATE = os.path.join(APP_DIR, 'modules', 'core', 'shared', 'templates', 'base.html')


def _user(app, client, db_session, email, role='admin'):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password('pw123456')
    db_session.add(user)
    db_session.commit()
    login_as(client, app, user, 'pw123456')
    return user


def _article(db_session, section, slug, help_key, published=True, title='A'):
    article = WikiArticle(section_id=section.id, title=title, slug=slug, help_key=help_key,
                          is_published=published,
                          sections_json=json.dumps({'time': 0, 'version': '2.30.7', 'blocks': [
                              {'id': 'a', 'type': 'paragraph', 'data': {'text': 'How you do it'}}
                          ]}))
    db_session.add(article)
    db_session.commit()
    return article


def _section(db_session, slug, published=True):
    section = WikiSection(title='S', slug=slug, is_published=published)
    db_session.add(section)
    db_session.commit()
    return section


# ------ The shell the tray mounts into ------

def test_dock_offers_a_help_launcher():
    """HelixTrays.open() does nothing without a launcher, so the pill is load-bearing."""
    markup = open(TRAY_DOCK, encoding='utf-8').read()
    assert 'data-tray="help"' in markup


def test_base_loads_the_help_tray_script():
    assert 'js/help_tray.js' in open(BASE_TEMPLATE, encoding='utf-8').read()


def test_help_button_macro_stamps_the_key_attribute():
    """The delegated click handler and the registry guard both read this attribute."""
    macros = open(SHARED_MACROS, encoding='utf-8').read()
    assert 'macro help_button' in macros
    assert 'data-help-key=' in macros


# ------ Reading an article through the tray ------

def test_help_route_renders_the_article(app, client, db_session):
    _user(app, client, db_session, 'help-read@example.com', role='designer')
    section = _section(db_session, 'h-read')
    _article(db_session, section, 'h-one', 'projects.submissions')

    resp = client.get('/wiki/help/projects.submissions')

    assert resp.status_code == 200
    assert b'How you do it' in resp.data
    assert b'projects.submissions' in resp.data


def test_help_route_requires_sign_in(client):
    resp = client.get('/wiki/help/projects.submissions')
    assert resp.status_code in (302, 401)


def test_unregistered_key_is_not_found(app, client, db_session):
    _user(app, client, db_session, 'help-unknown@example.com')
    assert client.get('/wiki/help/totally.made.up').status_code == 404


# ------ The gap, and the way to fill it ------

def test_admin_sees_the_write_shortcut(app, client, db_session):
    _user(app, client, db_session, 'help-admin@example.com')

    resp = client.get('/wiki/help/cs.invoicing')

    assert b'Nothing written yet' in resp.data
    assert b'Write this article' in resp.data
    assert b'help_key=cs.invoicing' in resp.data


def test_a_designer_sees_the_gap_but_no_shortcut(app, client, db_session):
    _user(app, client, db_session, 'help-designer@example.com', role='designer')

    resp = client.get('/wiki/help/cs.invoicing')

    assert b'Nothing written yet' in resp.data
    assert b'Write this article' not in resp.data


def test_an_unpublished_article_reads_as_a_gap_to_a_designer(app, client, db_session):
    _user(app, client, db_session, 'help-draft@example.com', role='designer')
    section = _section(db_session, 'h-draft')
    _article(db_session, section, 'h-draft-a', 'projects.flags', published=False)

    resp = client.get('/wiki/help/projects.flags')

    assert b'Nothing written yet' in resp.data
    assert b'How you do it' not in resp.data


def test_an_admin_can_read_their_own_draft(app, client, db_session):
    _user(app, client, db_session, 'help-draft-admin@example.com')
    section = _section(db_session, 'h-draft2')
    _article(db_session, section, 'h-draft-b', 'projects.flags', published=False)

    assert b'How you do it' in client.get('/wiki/help/projects.flags').data


# ------ Browsing ------

def test_browse_hides_unpublished_sections_from_a_designer(app, client, db_session):
    _user(app, client, db_session, 'help-browse@example.com', role='designer')
    hidden = _section(db_session, 'h-hidden', published=False)
    _article(db_session, hidden, 'h-hidden-a', None, title='Secret')

    resp = client.get('/wiki/help')

    assert resp.status_code == 200
    assert b'Secret' not in resp.data
