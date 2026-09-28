"""Login redirect safety, deactivated sessions, and the legacy password reset."""
import re

import pytest
from flask import url_for

from app.modules.core.shared.models import User, load_user
from app.modules.core.shared.testing import login_as


def _user(db_session, email, role='designer', password='password123'):
    user = User(name=email.split('@')[0], email=email, role=role)
    user.set_password(password)
    db_session.add(user)
    db_session.commit()
    return user, password


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def _post_login(client, app, user, password, next_value):
    return client.post(_url(app, 'auth.login'),
                       data={'email': user.email, 'password': password, 'next': next_value})


@pytest.mark.parametrize('next_value', [
    '//evil.com',
    '//evil.com/path',
    '\\\\evil.com',
    '/\\evil.com',
    '\\/evil.com',
    'https://evil.com/projects',
    'http://evil.com//evil2.com',
    'javascript:alert(1)',
    '/\t/evil.com',
])
def test_login_refuses_off_site_next(app, client, db_session, next_value):
    user, password = _user(db_session, 'redirect-guard@example.com')
    resp = _post_login(client, app, user, password, next_value)
    assert resp.status_code == 302
    location = resp.headers['Location']
    assert 'evil' not in location
    assert location.endswith(_url(app, 'projects.index'))


def test_login_follows_same_site_next(app, client, db_session):
    user, password = _user(db_session, 'redirect-ok@example.com')
    resp = _post_login(client, app, user, password, '/account?tab=sounds')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/account?tab=sounds')


def test_deactivated_user_loses_existing_session(app, client, db_session):
    user, password = _user(db_session, 'session-kill@example.com')
    login_as(client, app, user, password)
    account_url = _url(app, 'auth.account')
    assert client.get(account_url).status_code == 200

    user.is_active = False
    db_session.commit()

    resp = client.get(account_url)
    assert resp.status_code == 302
    assert _url(app, 'auth.login') in resp.headers['Location']


def test_load_user_refuses_a_deactivated_account(app, db_session):
    # login_required alone already bounces them (UserMixin.is_authenticated is
    # is_active); the loader refusing too keeps current_user anonymous everywhere.
    user, _ = _user(db_session, 'loader-kill@example.com')
    token = user.get_id()
    assert load_user(token) is not None
    user.is_active = False
    db_session.commit()
    assert load_user(token) is None


def test_legacy_reset_gives_a_fresh_password_each_time(app, client, db_session):
    admin, admin_pw = _user(db_session, 'legacy-reset-admin@example.com', role='admin')
    target, _ = _user(db_session, 'legacy-reset-target@example.com')
    login_as(client, app, admin, admin_pw)

    shown = []
    for _ in range(2):
        resp = client.post(_url(app, 'auth.reset_password', user_id=target.id),
                           follow_redirects=True)
        assert resp.status_code == 200
        match = re.search(r'reset to (\S+) —', resp.get_data(as_text=True))
        assert match, 'the new password is shown to the admin'
        shown.append(match.group(1))

    assert shown[0] != shown[1]
    assert 'Vitamin2026!' not in shown
    db_session.refresh(target)
    assert target.check_password(shown[1])
    assert not target.check_password(shown[0])
