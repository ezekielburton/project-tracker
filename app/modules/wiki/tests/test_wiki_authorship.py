"""Who wrote and last updated an article, and whether it was reviewed this quarter."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.modules.core.shared.models import User, WikiArticle, WikiSection
from app.modules.core.shared.testing import login_as
from app.modules.wiki.lib.freshness import review_label, reviewed_this_quarter

PW = 'pw123456'
DOC = json.dumps({'time': 0, 'version': '2.30.7', 'blocks': []})


def _admin(db_session, email, name):
    user = User(name=name, email=email, role='admin')
    user.set_password(PW)
    db_session.add(user)
    db_session.commit()
    return user


def _client(app, user):
    """Log in just before use: requests share the test's app context, so the
    latest login is who every request runs as."""
    client = app.test_client()
    login_as(client, app, user, PW)
    return client


def _section(db_session, slug):
    section = WikiSection(title='S', slug=slug, is_published=True)
    db_session.add(section)
    db_session.commit()
    return section


def _article(db_session, section, **fields):
    article = WikiArticle(section_id=section.id, title='T', slug='t', sections_json=DOC,
                          is_published=True, **fields)
    db_session.add(article)
    db_session.commit()
    return article


def _save(client, article, section, text):
    document = {'time': 0, 'version': '2.30.7',
                'blocks': [{'id': 'p', 'type': 'paragraph', 'data': {'text': text}}]}
    return client.post('/wiki/editor/article/save', data={
        'article_id': str(article.id), 'section_id': str(section.id), 'title': 'T',
        'sections_json': json.dumps(document), 'is_published': 'on',
    })


# ------ Recording who and when ------

def test_creating_records_the_author_and_updater(app, db_session):
    author = _admin(db_session, 'auth-create@example.com', 'Ada Writer')
    section = _section(db_session, 'auth-create')

    _client(app, author).post('/wiki/editor/article/create', data={
        'section_id': str(section.id), 'title': 'Fresh page', 'template': 'blank',
    })

    article = WikiArticle.query.filter_by(title='Fresh page').one()
    assert (article.created_by_id, article.updated_by_id) == (author.id, author.id)


def test_a_save_by_someone_else_changes_only_the_updater_and_review(app, db_session):
    author = _admin(db_session, 'auth-first@example.com', 'Ada Writer')
    editor = _admin(db_session, 'auth-second@example.com', 'Bo Editor')
    section = _section(db_session, 'auth-save')
    article = _article(db_session, section, created_by_id=author.id, updated_by_id=author.id,
                       reviewed_at=datetime.utcnow() - timedelta(days=200))

    _save(_client(app, editor), article, section, 'New words')
    db_session.expire_all()

    article = WikiArticle.query.get(article.id)
    assert article.created_by_id == author.id
    assert article.updated_by_id == editor.id
    assert reviewed_this_quarter(article.reviewed_at)


def test_autosave_records_nobody(app, db_session):
    author = _admin(db_session, 'auth-auto-1@example.com', 'Ada Writer')
    other = _admin(db_session, 'auth-auto-2@example.com', 'Bo Editor')
    section = _section(db_session, 'auth-autosave')
    old_review = datetime.utcnow() - timedelta(days=200)
    article = _article(db_session, section, created_by_id=author.id, updated_by_id=author.id,
                       reviewed_at=old_review)

    _client(app, other).post('/wiki/editor/article/autosave', data={
        'article_id': str(article.id), 'sections_json': DOC,
    })
    db_session.expire_all()

    article = WikiArticle.query.get(article.id)
    assert article.updated_by_id == author.id
    assert article.reviewed_at == old_review


def test_marking_reviewed_leaves_last_updated_alone(app, db_session):
    author = _admin(db_session, 'auth-review-1@example.com', 'Ada Writer')
    reviewer = _admin(db_session, 'auth-review-2@example.com', 'Bo Editor')
    section = _section(db_session, 'auth-review')
    article = _article(db_session, section, updated_by_id=author.id,
                       reviewed_at=datetime.utcnow() - timedelta(days=200))
    was_updated_at = article.updated_at

    resp = _client(app, reviewer).post(f'/wiki/editor/article/{article.id}/reviewed')
    db_session.expire_all()

    article = WikiArticle.query.get(article.id)
    assert resp.status_code == 302
    assert reviewed_this_quarter(article.reviewed_at)
    assert article.updated_at == was_updated_at
    assert article.updated_by_id == author.id


# ------ The quarter ------

def test_review_label_follows_the_calendar_quarter():
    end_of_march = datetime(2026, 3, 31, 23, 0)
    start_of_april = datetime(2026, 4, 1, 1, 0)

    assert review_label(end_of_march, now=datetime(2026, 3, 1)) == 'Reviewed this quarter'
    assert review_label(end_of_march, now=start_of_april) == 'Reviewed Mar 2026'
    assert review_label(start_of_april, now=datetime(2026, 6, 30)) == 'Reviewed this quarter'
    assert review_label(None) == ''


# ------ What people see ------

def _byline(app, **fields):
    article = SimpleNamespace(title='T', updated_at=datetime(2026, 9, 11), **fields)
    template = app.jinja_env.get_template('wiki/_article_content.html')
    return ' '.join(template.render(article=article, blocks=[]).split())


def test_byline_names_the_updater_and_the_review(app):
    html = _byline(app, updated_by=SimpleNamespace(name='Ezekiel Burton'),
                   reviewed_at=datetime.utcnow())
    assert 'Updated 11 Sep 2026 by Ezekiel · Reviewed this quarter' in html


def test_byline_without_an_updater_leaves_out_the_name(app):
    html = _byline(app, updated_by=None, reviewed_at=None)
    assert 'Updated 11 Sep 2026' in html
    assert ' by ' not in html and 'Reviewed' not in html


def test_only_stale_rows_say_review_due(app, db_session):
    admin = _admin(db_session, 'auth-due@example.com', 'Ada Writer')
    section = _section(db_session, 'auth-due')
    _article(db_session, section, reviewed_at=datetime.utcnow())
    stale = _article(db_session, section, reviewed_at=datetime.utcnow() - timedelta(days=200))

    html = _client(app, admin).get('/wiki/editor').get_data(as_text=True)

    assert html.count('wiki-review-badge') == 1
    assert f'/wiki/editor/article/{stale.id}/reviewed' in html
