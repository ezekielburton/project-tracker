"""Run now: real admin only (an emulating admin keeps it), listed jobs only,
POST only, and it leaves the trigger file a systemd path unit picks up."""
import os

import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as

PASSWORD = 'password123'


def _url(app, job_key):
    with app.test_request_context():
        return url_for('projects.admin_job_run_now', job_key=job_key)


def _user(db_session, tag, **org_fields):
    user = User(name=f'Run Now {tag}', email=f'run-now-{tag}@example.com', **org_fields)
    user.set_password(PASSWORD)
    db_session.add(user)
    db_session.flush()
    return user


def _trigger(app, job_key):
    path = os.path.join(app.config['RUN_NOW_DIR'], job_key)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return f.read()


@pytest.fixture(autouse=True)
def _no_triggers(app):
    folder = app.config['RUN_NOW_DIR']

    def clear():
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                os.remove(os.path.join(folder, name))
    clear()
    yield
    clear()


def test_run_now_refuses_a_logged_out_caller(app, client):
    assert client.post(_url(app, 'backup')).status_code == 403
    assert _trigger(app, 'backup') is None


def test_run_now_refuses_someone_who_is_not_admin(app, client, db_session):
    login_as(client, app, _user(db_session, 'designer', department='design'), PASSWORD)
    assert client.post(_url(app, 'backup')).status_code == 403
    assert _trigger(app, 'backup') is None


def test_an_admin_starts_a_job(app, client, db_session):
    admin = _user(db_session, 'admin', is_admin=True)
    login_as(client, app, admin, PASSWORD)
    response = client.post(_url(app, 'backup'))
    assert response.status_code == 200 and response.get_json()['success']
    assert _trigger(app, 'backup') == str(admin.id)


def test_an_emulating_admin_keeps_it_and_the_run_is_theirs(app, client, db_session):
    admin = _user(db_session, 'emu-admin', is_admin=True)
    designer = _user(db_session, 'emu-designer', department='design')
    login_as(client, app, admin, PASSWORD)
    with client.session_transaction() as session:
        session['emulating_user_id'] = designer.id
    assert client.post(_url(app, 'vacuum-analyze')).status_code == 200
    assert _trigger(app, 'vacuum-analyze') == str(admin.id)


def test_only_listed_jobs_that_may_run_by_hand(app, client, db_session):
    login_as(client, app, _user(db_session, 'list-admin', is_admin=True), PASSWORD)
    assert client.post(_url(app, 'heartbeat')).status_code == 400
    assert client.post(_url(app, 'no-such-job')).status_code == 404
    assert _trigger(app, 'heartbeat') is None


def test_run_now_is_post_only(app, client, db_session):
    login_as(client, app, _user(db_session, 'get-admin', is_admin=True), PASSWORD)
    assert client.get(_url(app, 'backup')).status_code == 405
