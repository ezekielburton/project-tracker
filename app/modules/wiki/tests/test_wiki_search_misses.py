"""Searches that find nothing: what gets recorded, the note, and the Write next panel."""
import json
from datetime import datetime, timedelta

import pytest

from app.modules.core.shared.models import User, WikiArticle, WikiSearchMiss, WikiSection
from app.modules.core.shared.testing import count_queries, login_as
from app.modules.wiki.lib.blocks import document_text
from app.modules.wiki.lib.search_misses import phrase_key, write_next

PW = 'pw123456'


def test_note_requires_login(client):
    resp = client.post('/wiki/search/miss/1/note', data={'note': 'x'})
    assert resp.status_code in (302, 401)


def _user(db_session, email, role='designer'):
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


def _search(client, q):
    return client.get('/wiki/search', query_string={'q': q})


def _article(db_session, body, published=True, slug='miss-section'):
    section = WikiSection(title='Section', slug=slug, is_published=True)
    db_session.add(section)
    db_session.commit()
    document = {'time': 0, 'version': '2.30.7',
                'blocks': [{'id': 'p', 'type': 'paragraph', 'data': {'text': body}}]}
    article = WikiArticle(section_id=section.id, title='Answer', slug='answer',
                          sections_json=json.dumps(document), search_text=document_text(document),
                          is_published=published)
    db_session.add(article)
    db_session.commit()
    return article


def _miss(db_session, phrase, user, note=None, days_ago=0):
    row = WikiSearchMiss(phrase=phrase, phrase_key=phrase_key(phrase), user_id=user.id, note=note,
                         created_at=datetime.utcnow() - timedelta(days=days_ago))
    db_session.add(row)
    db_session.commit()
    return row


def _misses():
    return WikiSearchMiss.query.order_by(WikiSearchMiss.id).all()


# ------ Recording ------

def test_a_search_that_finds_nothing_is_recorded(app, db_session):
    reader = _user(db_session, 'miss-record@example.com')

    _search(_client(app, reader), 'Invoice thresholds')

    [miss] = _misses()
    assert miss.phrase == 'Invoice thresholds'
    assert miss.phrase_key == phrase_key('invoice threshold')
    assert miss.user_id == reader.id


def test_nothing_found_counts_only_what_the_reader_could_search(app, db_session):
    reader = _user(db_session, 'miss-searched@example.com')
    _article(db_session, 'live words')
    _article(db_session, 'draft words', published=False, slug='miss-section-draft')

    body = _search(_client(app, reader), 'nothing here zz').get_data(as_text=True)

    assert 'Searched 1 article.' in body


@pytest.mark.parametrize('q', ['', '   ', 'the', 'kerfuffle'])
def test_empty_stopword_or_successful_searches_are_not_recorded(app, db_session, q):
    reader = _user(db_session, 'miss-none@example.com')
    _article(db_session, 'a kerfuffle explained')

    assert _search(_client(app, reader), q).status_code == 200
    assert _misses() == []


def test_admin_searches_are_not_recorded_even_while_emulating(app, db_session):
    admin = _user(db_session, 'miss-admin@example.com', role='admin')
    designer = _user(db_session, 'miss-emulated@example.com')

    _search(_client(app, admin), 'nothing here zz')
    _search(_client(app, admin, emulating=designer), 'nothing here zz')

    assert _misses() == []


def test_one_person_counts_once_a_day_and_each_person_counts(app, db_session):
    first = _user(db_session, 'miss-first@example.com')
    second = _user(db_session, 'miss-second@example.com')

    first_client = _client(app, first)
    _search(first_client, 'gazebo paint')
    _search(first_client, 'gazebo paint')

    second_client = _client(app, second)
    _search(second_client, 'painting gazebos')
    body = _search(second_client, 'painting gazebos').get_data(as_text=True)

    assert len(_misses()) == 2
    assert 'Asked 2 times this month by 2 people.' in body


def test_a_repeat_after_a_day_counts_again(app, db_session):
    reader = _user(db_session, 'miss-later@example.com')
    client = _client(app, reader)
    _search(client, 'gazebo paint')
    _misses()[0].created_at = datetime.utcnow() - timedelta(days=2)
    db_session.commit()

    _search(client, 'gazebo paint')

    assert len(_misses()) == 2


def test_wordings_of_one_question_share_a_key(db_session):
    assert phrase_key('Submitting decks') == phrase_key('submit deck') == phrase_key('deck submit')
    assert phrase_key('the') == ''


# ------ The note ------

def test_the_asker_can_say_what_they_were_after(app, db_session):
    reader = _user(db_session, 'miss-note@example.com')
    client = _client(app, reader)
    _search(client, 'zebra crossing')
    miss = _misses()[0]

    resp = client.post(f'/wiki/search/miss/{miss.id}/note', data={'note': 'x' * 900})
    db_session.expire_all()

    assert resp.status_code == 302
    assert WikiSearchMiss.query.get(miss.id).note == 'x' * 500
    body = _search(client, 'zebra crossing').get_data(as_text=True)
    assert 'Sent.' in body and 'name="note"' not in body


def test_nobody_else_can_write_on_someone_elses_search(app, db_session):
    asker = _user(db_session, 'miss-asker@example.com')
    other = _user(db_session, 'miss-other@example.com')
    admin = _user(db_session, 'miss-note-admin@example.com', role='admin')
    _search(_client(app, asker), 'zebra crossing')
    miss = _misses()[0]

    assert _client(app, other).post(f'/wiki/search/miss/{miss.id}/note',
                                    data={'note': 'hijack'}).status_code == 404
    assert _client(app, admin, emulating=asker).post(f'/wiki/search/miss/{miss.id}/note',
                                                     data={'note': 'hijack'}).status_code == 404
    db_session.expire_all()
    assert WikiSearchMiss.query.get(miss.id).note is None


# ------ Write next ------

def test_write_next_groups_and_counts_questions(db_session):
    first = _user(db_session, 'miss-wn1@example.com')
    second = _user(db_session, 'miss-wn2@example.com')
    _miss(db_session, 'gazebo paint', first, note='Which colour is allowed?')
    _miss(db_session, 'painting gazebos', second)
    _miss(db_session, 'gazebo paint', second, days_ago=2)

    [item] = write_next()

    assert (item.times, item.people) == (3, 2)
    assert item.phrase == 'gazebo paint'
    assert item.notes == ['Which colour is allowed?']


def test_a_question_drops_off_once_a_published_article_answers_it(db_session):
    reader = _user(db_session, 'miss-answered@example.com')
    _miss(db_session, 'walrus feeding', reader)
    _article(db_session, 'walrus feeding times', published=False)
    assert len(write_next()) == 1

    _article(db_session, 'walrus feeding times', slug='miss-section-2')
    assert write_next() == []


def test_old_questions_are_left_out(db_session):
    reader = _user(db_session, 'miss-old@example.com')
    _miss(db_session, 'ancient question', reader, days_ago=100)
    assert write_next() == []


def test_dismissed_questions_leave_the_panel(app, db_session):
    reader = _user(db_session, 'miss-dismiss@example.com')
    admin = _user(db_session, 'miss-dismiss-admin@example.com', role='admin')
    _miss(db_session, 'asdf qwer', reader)
    client = _client(app, admin)

    assert 'asdf qwer' in client.get('/wiki/editor').get_data(as_text=True)
    client.post('/wiki/editor/misses/dismiss', data={'phrase_key': phrase_key('asdf qwer')})

    assert write_next() == []


def test_write_next_query_count_does_not_grow_with_questions(db_session):
    reader = _user(db_session, 'miss-count@example.com')
    for i in range(2):
        _miss(db_session, f'question number{i}x', reader, note='why')
    with count_queries() as few:
        write_next()

    for i in range(2, 8):
        _miss(db_session, f'question number{i}x', reader, note='why')
    with count_queries() as many:
        items = write_next()

    assert len(items) == 8
    assert many[0] == few[0]
