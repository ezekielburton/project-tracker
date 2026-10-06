"""People start on their dashboard, or on their own module when they have no
dashboard: the HSE officer lands on HSE after login and on '/'."""
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as

PASSWORD = 'password123'


def _user(db_session, tag, role):
    user = User(name=f'Home {tag}', email=f'home-{tag}@example.com', role=role)
    user.set_password(PASSWORD)
    db_session.add(user)
    db_session.flush()
    return user


def _url(app, endpoint):
    with app.test_request_context():
        return url_for(endpoint)


def _post_login(client, app, user):
    return client.post(_url(app, 'auth.login'), data={'email': user.email, 'password': PASSWORD})


def test_the_hse_officer_lands_on_hse_after_login(app, client, db_session):
    resp = _post_login(client, app, _user(db_session, 'officer-login', 'hse'))
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith(_url(app, 'hse.overview'))


def test_hr_reads_hse_but_still_lands_on_the_dashboard(app, client, db_session):
    resp = _post_login(client, app, _user(db_session, 'hr-login', 'hr'))
    assert resp.headers['Location'].endswith(_url(app, 'projects.index'))


def test_the_root_sends_the_officer_to_hse(app, client, db_session):
    login_as(client, app, _user(db_session, 'officer-root', 'hse'), PASSWORD)
    assert client.get('/').headers['Location'].endswith(_url(app, 'hse.overview'))


def test_the_root_sends_staff_to_the_dashboard(app, client, db_session):
    login_as(client, app, _user(db_session, 'designer-root', 'designer'), PASSWORD)
    assert client.get('/').headers['Location'].endswith(_url(app, 'projects.index'))
