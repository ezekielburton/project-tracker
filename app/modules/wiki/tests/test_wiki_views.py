"""Reads: counted once per person per day, never for wiki managers, shown on the byline and Most read."""
import json
import re
from datetime import datetime, timedelta

from app.modules.core.shared.models import User, WikiArticle, WikiArticleView, WikiSection
from app.modules.core.shared.testing import count_queries, login_as
from app.modules.wiki.lib.views import most_read

PW = 'pw123456'
DOC = json.dumps({'time': 0, 'version': '2.30.7', 'blocks': []})


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


def _articles(db_session, count=1, published=True):
    section = WikiSection(title='Reads', slug='reads-section', is_published=True)
    db_session.add(section)
    db_session.commit()
    articles = []
    for i in range(count):
        article = WikiArticle(section_id=section.id, title=f'Read me {i}', slug=f'read-me-{i}',
                              sections_json=DOC, is_published=published, sort_order=i)
        db_session.add(article)
        articles.append(article)
    db_session.commit()
    return articles


def _views(article):
    return WikiArticleView.query.filter_by(article_id=article.id).all()


def _seed(db_session, article, reads, days_ago=0):
    for _ in range(reads):
        db_session.add(WikiArticleView(article_id=article.id, source='page',
                                       viewed_at=datetime.utcnow() - timedelta(days=days_ago)))
    db_session.commit()


# ------ Recording ------

def test_a_read_counts_once_a_day_whichever_way_it_was_opened(app, db_session):
    [article] = _articles(db_session)
    client = _client(app, _user(db_session, 'views-once@example.com'))

    client.get(f'/wiki/article/{article.id}')
    client.get(f'/wiki/article/{article.id}')
    client.get(f'/wiki/help/article/{article.id}')

    [view] = _views(article)
    assert view.source == 'page'


def test_the_help_tray_records_its_own_reads(app, db_session):
    [article] = _articles(db_session)
    _client(app, _user(db_session, 'views-tray@example.com')).get(f'/wiki/help/article/{article.id}')
    assert [view.source for view in _views(article)] == ['tray']


def test_a_read_counts_again_after_a_day(app, db_session):
    [article] = _articles(db_session)
    client = _client(app, _user(db_session, 'views-again@example.com'))
    client.get(f'/wiki/article/{article.id}')
    _views(article)[0].viewed_at = datetime.utcnow() - timedelta(days=2)
    db_session.commit()

    client.get(f'/wiki/article/{article.id}')

    assert len(_views(article)) == 2


def test_wiki_managers_reads_are_not_counted_even_while_emulating(app, db_session):
    [article] = _articles(db_session)
    admin = _user(db_session, 'views-admin@example.com', role='admin')
    designer = _user(db_session, 'views-emulated@example.com')

    _client(app, admin).get(f'/wiki/article/{article.id}')
    _client(app, admin, emulating=designer).get(f'/wiki/article/{article.id}')

    assert _views(article) == []


def test_deleting_an_article_deletes_its_reads(app, db_session):
    [article] = _articles(db_session)
    _seed(db_session, article, 2)
    article_id = article.id

    db_session.delete(article)
    db_session.commit()

    assert WikiArticleView.query.filter_by(article_id=article_id).count() == 0


# ------ Showing ------

def test_the_byline_shows_the_read_count(app, db_session):
    [article] = _articles(db_session)
    _seed(db_session, article, 4, days_ago=3)

    body = _client(app, _user(db_session, 'views-byline@example.com')).get(f'/wiki/article/{article.id}').get_data(as_text=True)

    assert '· 5 reads' in body


def test_most_read_ranks_this_months_reads_and_caps_the_list(db_session):
    articles = _articles(db_session, count=7)
    for reads, article in zip((1, 6, 3, 2, 5, 4, 7), articles):
        _seed(db_session, article, reads)
    _seed(db_session, articles[0], 50, days_ago=40)

    ranked = most_read([article.id for article in articles])

    assert ranked == [(articles[6].id, 7), (articles[1].id, 6), (articles[4].id, 5),
                      (articles[5].id, 4), (articles[2].id, 3)]


def test_most_read_takes_one_query_however_many_articles(db_session):
    articles = _articles(db_session, count=8)
    for article in articles:
        _seed(db_session, article, 1)
    ids = [article.id for article in articles]
    with count_queries() as few:
        most_read(ids[:2])
    with count_queries() as many:
        most_read(ids)
    assert many[0] == few[0]


def test_the_home_page_lists_most_read_and_never_a_draft_for_readers(app, db_session):
    live = _articles(db_session, count=2)
    draft = WikiArticle(section_id=live[0].section_id, title='Unpublished hit', slug='unpublished-hit',
                        sections_json=DOC, is_published=False)
    db_session.add(draft)
    db_session.commit()
    _seed(db_session, live[1], 3)
    _seed(db_session, live[0], 1)
    _seed(db_session, draft, 9)

    body = _client(app, _user(db_session, 'views-home@example.com')).get('/wiki').get_data(as_text=True)
    popular = body[body.index('wiki-popular'):]

    assert re.findall(r'<a [^>]*>([^<]+)</a>', popular)[:2] == ['Read me 1', 'Read me 0']
    assert 'Unpublished hit' not in body


def test_no_reads_means_no_most_read_panel(app, db_session):
    _articles(db_session)
    body = _client(app, _user(db_session, 'views-none@example.com')).get('/wiki').get_data(as_text=True)
    assert 'wiki-popular' not in body
