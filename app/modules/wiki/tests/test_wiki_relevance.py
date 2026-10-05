"""Role relevance in the reader: other roles' sections dim and sort later; nothing is hidden."""
import json
import re
from types import SimpleNamespace

import pytest

from app.modules.core.shared.lib.capabilities import ROLE_LABELS
from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as
from app.modules.wiki.lib.blocks import document_text
from app.modules.wiki.lib.relevance import is_for, section_roles
from app.modules.wiki.lib.search import search_articles

PW = 'pw123456'
TITLES = ('Designer guide', 'CS guide', 'Shared guide')


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


def _sections(db_session):
    """One section for designers, one for CS, one for everyone; each with a 'gazebo' article."""
    for slug, roles, title in (('rel-designer', 'designer', 'Designer guide'),
                               ('rel-cs', 'cs', 'CS guide'),
                               ('rel-everyone', None, 'Shared guide')):
        section = WikiSection(title=slug, slug=slug, relevant_roles=roles, is_published=True)
        db_session.add(section)
        db_session.commit()
        document = {'time': 0, 'version': '2.30.7',
                    'blocks': [{'id': 'p', 'type': 'paragraph', 'data': {'text': 'gazebo care'}}]}
        db_session.add(WikiArticle(section_id=section.id, title=title, slug=slug,
                                   sections_json=json.dumps(document),
                                   search_text=document_text(document), is_published=True))
        db_session.commit()


# ------ Reading a section's roles ------

def test_section_roles_reads_keys_and_old_labels_and_ignores_the_rest():
    section = SimpleNamespace(relevant_roles='designer, Client Servicing, nonsense, designer')
    assert section_roles(section) == ['designer', 'cs']
    assert section_roles(SimpleNamespace(relevant_roles=None)) == []


def test_section_roles_reads_the_original_pickers_values():
    """The first section picker saved these exact strings; every one must still resolve."""
    section = SimpleNamespace(relevant_roles='Admin,CS,Designer,Team Lead,Management')
    assert section_roles(section) == ['admin', 'cs', 'designer', 'team_lead', 'management']


def test_a_section_with_no_roles_is_for_everyone():
    assert is_for(SimpleNamespace(relevant_roles=''), 'hse')
    assert not is_for(SimpleNamespace(relevant_roles='cs'), 'designer')


# ------ Nothing is hidden ------

@pytest.mark.parametrize('role', list(ROLE_LABELS))
@pytest.mark.parametrize('scope', ['mine', 'all'])
def test_role_filtering_hides_nothing(app, db_session, role, scope):
    _sections(db_session)
    client = _client(app, _user(db_session, f'rel-{role}-{scope}@example.com', role))

    page = client.get('/wiki', query_string={'scope': scope}).get_data(as_text=True)
    results = client.get('/wiki/search', query_string={'q': 'gazebo', 'scope': scope}).get_data(as_text=True)

    for title in TITLES:
        assert title in page
        assert title in results


def _results(body):
    """Only the search results, so titles in the rail above them don't count."""
    return body[body.index('class="wiki-search__results"'):]


# ------ Search ------

def test_a_designer_sees_their_own_results_first_and_others_dimmed(app, db_session):
    _sections(db_session)
    client = _client(app, _user(db_session, 'rel-search@example.com', 'designer'))

    body = _results(client.get('/wiki/search', query_string={'q': 'gazebo'}).get_data(as_text=True))

    assert body.index('Designer guide') < body.index('CS guide')
    assert body.index('Shared guide') < body.index('CS guide')
    assert body.count('wiki-other-role') == 1
    assert 'for Client Servicing' in body


def test_everything_is_plain_match_order_with_nothing_dimmed(app, db_session):
    _sections(db_session)
    client = _client(app, _user(db_session, 'rel-all@example.com', 'designer'))

    page = client.get('/wiki/search', query_string={'q': 'gazebo', 'scope': 'all'}).get_data(as_text=True)
    body = _results(page)

    expected = [hit.article.title for hit in search_articles('gazebo')]
    assert sorted(expected, key=body.index) == expected
    assert 'wiki-other-role' not in body
    assert 'name="scope" value="all"' in page


# ------ The nav and the default ------

CLOSED = 'module-rail-children--closed'


def test_the_rail_collapses_other_roles_only_while_scoped(app, db_session):
    _sections(db_session)
    client = _client(app, _user(db_session, 'rel-nav@example.com', 'designer'))

    assert client.get('/wiki').get_data(as_text=True).count(CLOSED) == 1
    assert CLOSED not in client.get('/wiki?scope=all').get_data(as_text=True)


def test_wiki_managers_default_to_everything(app, db_session):
    _sections(db_session)
    body = _client(app, _user(db_session, 'rel-admin@example.com', 'admin')).get('/wiki').get_data(as_text=True)

    assert CLOSED not in body
    assert re.search(r'aria-current="true"\s+href="/wiki\?scope=all"', body)


def test_an_admin_emulating_a_designer_gets_the_designers_view(app, db_session):
    _sections(db_session)
    admin = _user(db_session, 'rel-emu-admin@example.com', 'admin')
    designer = _user(db_session, 'rel-emu-designer@example.com', 'designer')

    body = _client(app, admin, emulating=designer).get('/wiki').get_data(as_text=True)

    assert body.count(CLOSED) == 1
    assert '>Designer</a>' in body


def test_starting_to_emulate_lands_on_the_emulated_readers_default(app, db_session):
    """An admin's Everything is never written into links, so emulating a role collapses its others."""
    _sections(db_session)
    admin = _user(db_session, 'rel-switch-admin@example.com', 'admin')
    owner = _user(db_session, 'rel-switch-owner@example.com', 'project_owner')

    admin_page = _client(app, admin).get('/wiki').get_data(as_text=True)
    assert 'scope=all' not in admin_page.replace('href="/wiki?scope=all"', '')

    owner_view = _client(app, admin, emulating=owner).get('/wiki').get_data(as_text=True)
    assert owner_view.count(CLOSED) == 2


def test_an_explicit_choice_is_carried_in_links(app, db_session):
    _sections(db_session)
    body = _client(app, _user(db_session, 'rel-carry@example.com', 'designer')) \
        .get('/wiki?scope=all').get_data(as_text=True)
    assert '/wiki/search?scope=all' in body
