"""Wiki search: the words index rebuilt on save, matching, snippets, and who sees what."""
import json

import pytest

from app.modules.core.shared.lib.capabilities import ROLE_LABELS
from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import count_queries, login_as
from app.modules.wiki.lib.article_templates import template_document
from app.modules.wiki.lib.blocks import document_text
from app.modules.wiki.lib.search import MARK_START, MARK_STOP, highlight_snippet, search_articles

PW = 'pw123456'


def test_search_requires_login(client):
    resp = client.get('/wiki/search?q=anything')
    assert resp.status_code in (302, 401)


def _user(db_session, email, role):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password(PW)
    db_session.add(user)
    db_session.commit()
    return user


def _document(*blocks):
    return {'time': 0, 'version': '2.30.7', 'blocks': list(blocks)}


def _paragraph(text):
    return {'id': 'p', 'type': 'paragraph', 'data': {'text': text}}


def _section(db_session, slug, published=True):
    section = WikiSection(title=slug.replace('-', ' ').title(), slug=slug, is_published=published)
    db_session.add(section)
    db_session.commit()
    return section


def _article(db_session, section, title, body, published=True):
    document = _document(_paragraph(body))
    article = WikiArticle(section_id=section.id, title=title, slug=title.lower().replace(' ', '-'),
                          sections_json=json.dumps(document), search_text=document_text(document),
                          is_published=published)
    db_session.add(article)
    db_session.commit()
    return article


def _search(app, user, q, emulating=None):
    """Each call gets its own client, so one login never leaks into the next."""
    client = app.test_client()
    login_as(client, app, user, PW)
    if emulating is not None:
        with client.session_transaction() as sess:
            sess['emulating_user_id'] = emulating.id
    return client.get('/wiki/search', query_string={'q': q})


# ------ The words index ------

def test_document_text_reads_every_text_block():
    text = document_text(_document(
        _paragraph('Drag the <b>deck</b> in<br>then press Submit &amp; wait'),
        {'type': 'header', 'data': {'text': 'Before you start', 'level': 3}},
        {'type': 'helixCallout', 'data': {'text': 'Mind the deadline', 'variant': 'default'}},
        {'type': 'list', 'data': {'style': 'unordered', 'items': ['First step', {'content': 'Second step'}]}},
        {'type': 'image', 'data': {'file': {'url': '/static/x.png'}, 'caption': 'The upload box'}},
        {'type': 'helixVideo', 'data': {'source': 'embed', 'url': 'https://youtu.be/abc'}},
    ))
    for words in ('Drag the deck in then press Submit & wait', 'Before you start',
                  'Mind the deadline', 'First step', 'Second step', 'The upload box'):
        assert words in text
    assert '<' not in text and 'youtu' not in text and '/static' not in text


def test_saving_rebuilds_the_words_index(app, client, db_session):
    admin = _user(db_session, 'search-save@example.com', 'admin')
    login_as(client, app, admin, PW)
    section = _section(db_session, 'search-save')
    article = _article(db_session, section, 'Rebuilt', 'oldword stays here')

    client.post('/wiki/editor/article/save', data={
        'article_id': str(article.id), 'section_id': str(section.id), 'title': 'Rebuilt',
        'sections_json': json.dumps(_document(_paragraph('freshword arrives'))),
        'is_published': 'on',
    })
    db_session.expire_all()

    assert article.id in [hit.article.id for hit in search_articles('freshword')]
    assert article.id not in [hit.article.id for hit in search_articles('oldword')]


def test_autosave_leaves_the_words_index_alone(app, client, db_session):
    admin = _user(db_session, 'search-autosave@example.com', 'admin')
    login_as(client, app, admin, PW)
    section = _section(db_session, 'search-autosave')
    article = _article(db_session, section, 'Kept', 'liveword stays here')

    client.post('/wiki/editor/article/autosave', data={
        'article_id': str(article.id),
        'sections_json': json.dumps(_document(_paragraph('draftonly words'))),
    })
    db_session.expire_all()

    assert search_articles('draftonly', include_drafts=True) == []
    assert search_articles('liveword', include_drafts=True)


def test_a_new_article_is_indexed_from_its_template(app, client, db_session):
    admin = _user(db_session, 'search-create@example.com', 'admin')
    login_as(client, app, admin, PW)
    section = _section(db_session, 'search-create')

    client.post('/wiki/editor/article/create', data={
        'section_id': str(section.id), 'title': 'Quokka guide', 'template': 'how-to',
    })
    db_session.expire_all()

    article = WikiArticle.query.filter_by(title='Quokka guide').one()
    assert article.search_text == document_text(template_document('how-to'))


# ------ Matching and snippets ------

def test_search_finds_an_article_by_a_word_only_in_its_body(app, db_session):
    reader = _user(db_session, 'search-body@example.com', 'designer')
    section = _section(db_session, 'search-body')
    _article(db_session, section, 'Submitting a draft', 'Attach the kerfuffle file before you send it')

    body = _search(app, reader, 'kerfuffle').get_data(as_text=True)

    assert 'Submitting a draft' in body
    assert '<mark>kerfuffle</mark>' in body


def test_search_matches_other_forms_of_a_word(db_session):
    section = _section(db_session, 'search-stem')
    _article(db_session, section, 'After review', 'Once the deck is submitted it goes to the client')

    assert [hit.article.title for hit in search_articles('submit')] == ['After review']


def test_a_title_match_outranks_a_body_match(db_session):
    section = _section(db_session, 'search-rank')
    _article(db_session, section, 'Ordinary page', 'Mentions zeppelin once in passing')
    _article(db_session, section, 'Zeppelin basics', 'All about airships')

    assert [hit.article.title for hit in search_articles('zeppelin')] == ['Zeppelin basics', 'Ordinary page']


def test_snippet_is_escaped_before_it_is_marked():
    raw = f'press <b>go</b> then {MARK_START}submit{MARK_STOP}'
    assert str(highlight_snippet(raw)) == 'press &lt;b&gt;go&lt;/b&gt; then <mark>submit</mark>'


def test_article_text_cannot_inject_markup(app, db_session):
    reader = _user(db_session, 'search-escape@example.com', 'designer')
    section = _section(db_session, 'search-escape')
    _article(db_session, section, 'Escaped', '&lt;script&gt;alert(1)&lt;/script&gt; kerfuffle')

    body = _search(app, reader, 'kerfuffle').get_data(as_text=True)

    assert '<script>alert' not in body


@pytest.mark.parametrize('q', ['', '   ', 'the', '( & | ! - "'])
def test_queries_without_real_words_show_no_results(app, db_session, q):
    reader = _user(db_session, 'search-odd@example.com', 'designer')
    section = _section(db_session, 'search-odd')
    _article(db_session, section, 'Anything', 'the open door')

    resp = _search(app, reader, q)

    assert resp.status_code == 200
    assert 'wiki-search__hit' not in resp.get_data(as_text=True)


def test_punctuation_around_a_real_word_still_finds_it(app, db_session):
    reader = _user(db_session, 'search-punct@example.com', 'designer')
    section = _section(db_session, 'search-punct')
    _article(db_session, section, 'Anything', 'the open door')

    resp = _search(app, reader, '"open ( & | ! -')

    assert resp.status_code == 200
    assert 'Anything' in resp.get_data(as_text=True)


def test_query_count_does_not_grow_with_results(db_session):
    section = _section(db_session, 'search-count')
    for i in range(2):
        _article(db_session, section, f'Gazebo {i}', 'gazebo care')
    with count_queries() as few:
        [hit.section.title for hit in search_articles('gazebo')]

    for i in range(2, 8):
        _article(db_session, section, f'Gazebo {i}', 'gazebo care')
    with count_queries() as many:
        hits = search_articles('gazebo')
        [hit.section.title for hit in hits]

    assert len(hits) == 8
    assert many[0] == few[0]


# ------ Who sees what ------

def _walrus_rows(db_session):
    live = _section(db_session, 'search-live')
    hidden = _section(db_session, 'search-hidden', published=False)
    _article(db_session, live, 'Published walrus', 'walrus facts')
    _article(db_session, live, 'Draft walrus', 'walrus notes', published=False)
    _article(db_session, hidden, 'Tucked walrus', 'walrus extras')


def test_readers_never_see_drafts_or_unpublished_sections(app, db_session):
    designer = _user(db_session, 'search-designer@example.com', 'designer')
    _walrus_rows(db_session)

    body = _search(app, designer, 'walrus').get_data(as_text=True)

    assert 'Published walrus' in body
    assert 'Draft walrus' not in body
    assert 'Tucked walrus' not in body


def test_admin_sees_drafts_marked_as_drafts(app, db_session):
    admin = _user(db_session, 'search-admin@example.com', 'admin')
    _walrus_rows(db_session)

    body = _search(app, admin, 'walrus').get_data(as_text=True)

    for title in ('Published walrus', 'Draft walrus', 'Tucked walrus'):
        assert title in body
    assert body.count('wiki-draft-badge') == 2


def test_admin_emulating_a_designer_sees_what_the_designer_sees(app, db_session):
    admin = _user(db_session, 'search-emu-admin@example.com', 'admin')
    designer = _user(db_session, 'search-emu-designer@example.com', 'designer')
    _walrus_rows(db_session)

    body = _search(app, admin, 'walrus', emulating=designer).get_data(as_text=True)

    assert 'Published walrus' in body
    assert 'Draft walrus' not in body
    assert 'Tucked walrus' not in body


@pytest.mark.parametrize('role', list(ROLE_LABELS))
def test_every_role_can_search(app, db_session, role):
    """The wiki is for everyone signed in, the HSE officer included."""
    user = _user(db_session, f'search-role-{role}@example.com', role)
    assert _search(app, user, 'anything').status_code == 200
