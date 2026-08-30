"""Tests for the theme-preference save route and its no-flash server render (2.4.1)."""
from flask import url_for
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


def _make_user(db_session, email='theme-test@example.com', password='pw123456'):
    user = User(name='Theme Tester', email=email, role='designer')
    user.set_password(password)
    db_session.add(user)
    db_session.commit()
    return user, password


def test_theme_prefs_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('auth.save_theme_prefs')
    resp = client.post(url, json={'theme': 'dark'})
    assert resp.status_code in (302, 401)


def test_theme_prefs_saves_valid_value(app, client, db_session):
    user, password = _make_user(db_session)
    login_as(client, app, user, password)

    with app.test_request_context():
        url = url_for('auth.save_theme_prefs')
    resp = client.post(url, json={'theme': 'dark'})

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert User.query.get(user.id).theme_preference == 'dark'


def test_theme_prefs_rejects_invalid_value(app, client, db_session):
    user, password = _make_user(db_session, email='theme-test2@example.com')
    login_as(client, app, user, password)

    with app.test_request_context():
        url = url_for('auth.save_theme_prefs')
    resp = client.post(url, json={'theme': 'blue'})

    assert resp.status_code == 400
    assert User.query.get(user.id).theme_preference is None


def test_saved_theme_renders_on_html_tag(app, client, db_session):
    """Server-side render of <html data-theme="..."> — the no-flash fallback
    for a fresh device that hasn't run the localStorage script yet."""
    user, password = _make_user(db_session, email='theme-test3@example.com')
    user.theme_preference = 'dark'
    db_session.commit()
    login_as(client, app, user, password)

    with app.test_request_context():
        url = url_for('auth.account')
    resp = client.get(url)

    assert b'data-theme="dark"' in resp.data
