"""The "Useful?" vote: one answer per reader, never wiki managers, and "no" lands on Write next."""
import json
from datetime import datetime, timedelta

from app.modules.core.shared.models import User, WikiArticle, WikiArticleVote, WikiSection
from app.modules.core.shared.testing import count_queries, login_as
from app.modules.wiki.lib.votes import cast_vote, not_useful

PW = 'pw123456'
DOC = json.dumps({'time': 0, 'version': '2.30.7', 'blocks': []})


def test_voting_requires_login(client):
    assert client.post('/wiki/article/1/vote', data={'helpful': 'yes'}).status_code in (302, 401)


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


def _article(db_session, title='Voted on', published=True, updated_days_ago=5):
    section = WikiSection(title='Votes', slug=f'votes-{title.lower().replace(" ", "-")}', is_published=True)
    db_session.add(section)
    db_session.commit()
    article = WikiArticle(section_id=section.id, title=title, slug=title.lower().replace(' ', '-'),
                          sections_json=DOC, is_published=published,
                          updated_at=datetime.utcnow() - timedelta(days=updated_days_ago))
    db_session.add(article)
    db_session.commit()
    return article


def _vote(app, user, article, **form):
    return _client(app, user).post(f'/wiki/article/{article.id}/vote', data=form)


def _votes(article):
    return WikiArticleVote.query.filter_by(article_id=article.id).all()


# ------ Casting ------

def test_one_answer_per_person_which_they_can_change(app, db_session):
    article = _article(db_session)
    reader = _user(db_session, 'vote-change@example.com')

    _vote(app, reader, article, helpful='no', note='x' * 900)
    [vote] = _votes(article)
    assert (vote.helpful, vote.note) == (False, 'x' * 500)

    _vote(app, reader, article, helpful='yes')
    db_session.expire_all()
    [vote] = _votes(article)
    assert (vote.helpful, vote.note) == (True, None)


def test_the_vote_returns_to_the_article(app, db_session):
    article = _article(db_session)
    resp = _vote(app, _user(db_session, 'vote-back@example.com'), article, helpful='yes')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith(f'/wiki/article/{article.id}#wiki-useful')


def test_wiki_managers_cannot_vote_even_while_emulating(app, db_session):
    article = _article(db_session)
    admin = _user(db_session, 'vote-admin@example.com', role='admin')
    designer = _user(db_session, 'vote-emulated@example.com')

    assert _vote(app, admin, article, helpful='no').status_code == 403
    resp = _client(app, admin, emulating=designer).post(f'/wiki/article/{article.id}/vote',
                                                       data={'helpful': 'no'})
    assert resp.status_code == 403
    assert _votes(article) == []


def test_drafts_and_missing_articles_take_no_votes(app, db_session):
    draft = _article(db_session, title='Draft page', published=False)
    reader = _user(db_session, 'vote-draft@example.com')
    assert _vote(app, reader, draft, helpful='yes').status_code == 403
    assert _client(app, reader).post('/wiki/article/999999/vote', data={'helpful': 'yes'}).status_code == 404


# ------ What readers see ------

def test_readers_see_the_question_and_wiki_managers_do_not(app, db_session):
    article = _article(db_session)
    reader_page = _client(app, _user(db_session, 'vote-see@example.com')).get(f'/wiki/article/{article.id}')
    admin_page = _client(app, _user(db_session, 'vote-see-admin@example.com', role='admin')).get(f'/wiki/article/{article.id}')

    assert 'Useful?' in reader_page.get_data(as_text=True)
    assert 'Useful?' not in admin_page.get_data(as_text=True)


def test_a_no_asks_what_was_missing_then_says_sent(app, db_session):
    article = _article(db_session)
    reader = _user(db_session, 'vote-flow@example.com')
    client = _client(app, reader)

    client.post(f'/wiki/article/{article.id}/vote', data={'helpful': 'no'})
    assert 'What was missing?' in client.get(f'/wiki/article/{article.id}').get_data(as_text=True)

    client.post(f'/wiki/article/{article.id}/vote', data={'helpful': 'no', 'note': 'The steps for C&CM'})
    body = client.get(f'/wiki/article/{article.id}').get_data(as_text=True)
    assert 'Sent.' in body and 'What was missing?' not in body


# ------ Write next ------

def test_not_useful_lists_noes_since_the_last_save(db_session):
    article = _article(db_session)
    first = _user(db_session, 'vote-wn1@example.com')
    second = _user(db_session, 'vote-wn2@example.com')
    third = _user(db_session, 'vote-wn3@example.com')
    cast_vote(article.id, first.id, False, 'Needs the C&CM steps')
    cast_vote(article.id, second.id, False)
    cast_vote(article.id, third.id, True)

    [item] = not_useful()

    assert item.article.id == article.id
    assert item.noes == 2
    assert item.notes == ['Needs the C&CM steps']


def test_saving_the_article_clears_it_from_not_useful(db_session):
    article = _article(db_session)
    cast_vote(article.id, _user(db_session, 'vote-clear@example.com').id, False)
    assert len(not_useful()) == 1

    article.updated_at = datetime.utcnow() + timedelta(minutes=1)
    db_session.commit()

    assert not_useful() == []


def test_the_dashboard_shows_not_useful_articles(app, db_session):
    article = _article(db_session, title='Confusing page')
    cast_vote(article.id, _user(db_session, 'vote-dash@example.com').id, False, 'Unclear')

    body = _client(app, _user(db_session, 'vote-dash-admin@example.com', role='admin')).get('/wiki/editor').get_data(as_text=True)

    assert 'Confusing page' in body
    assert '1 × no' in body
    assert 'Unclear' in body


def test_not_useful_query_count_does_not_grow_with_articles(db_session):
    reader = _user(db_session, 'vote-count@example.com')
    articles = [_article(db_session, title=f'Page {i}') for i in range(8)]
    for article in articles:
        cast_vote(article.id, reader.id, False, 'why')
    with count_queries() as many:
        items = not_useful()
    for article in articles[2:]:
        article.updated_at = datetime.utcnow() + timedelta(minutes=1)
    db_session.commit()
    with count_queries() as few:
        not_useful()
    assert len(items) == 8
    assert many[0] == few[0]
