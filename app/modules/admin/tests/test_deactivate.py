"""Account deactivation: the picker helper, the login block, and the admin toggle."""
from flask import url_for
from app.modules.core.shared.models import User
from app.modules.core.shared.lib.users import active_users_query
from app.modules.core.shared.testing import login_as


def _make_user(db_session, email, role='designer', password='pw123456', is_active=True):
    user = User(name=email.split('@')[0], email=email, role=role, is_active=is_active)
    user.set_password(password)
    db_session.add(user)
    db_session.commit()
    return user, password


def test_active_users_query_excludes_deactivated(app, client, db_session):
    active, _ = _make_user(db_session, 'active@example.com')
    inactive, _ = _make_user(db_session, 'inactive@example.com', is_active=False)
    ids = [u.id for u in active_users_query().all()]
    assert active.id in ids
    assert inactive.id not in ids


def test_deactivated_user_cannot_log_in(app, client, db_session):
    user, password = _make_user(db_session, 'gone@example.com', is_active=False)
    login_as(client, app, user, password)  # correct password, but account is off
    with app.test_request_context():
        account_url = url_for('auth.account')
    resp = client.get(account_url)
    assert resp.status_code in (302, 401)  # not authenticated → bounced to login


def test_admin_can_deactivate_and_reactivate(app, client, db_session):
    admin, admin_pw = _make_user(db_session, 'admin@example.com', role='admin')
    target, _ = _make_user(db_session, 'target@example.com')
    login_as(client, app, admin, admin_pw)

    url = f'/admin/api/users/{target.id}/active'
    resp = client.post(url, json={'active': False})
    assert resp.status_code == 200
    assert resp.get_json()['is_active'] is False
    assert User.query.get(target.id).is_active is False

    resp = client.post(url, json={'active': True})
    assert resp.status_code == 200
    assert User.query.get(target.id).is_active is True


def test_deactivate_route_is_admin_only(app, client, db_session):
    plain, plain_pw = _make_user(db_session, 'plain@example.com')
    target, _ = _make_user(db_session, 'target2@example.com')
    login_as(client, app, plain, plain_pw)
    resp = client.post(f'/admin/api/users/{target.id}/active', json={'active': False})
    assert resp.status_code == 403
    assert User.query.get(target.id).is_active is True


def test_admin_cannot_deactivate_self(app, client, db_session):
    admin, admin_pw = _make_user(db_session, 'admin2@example.com', role='admin')
    login_as(client, app, admin, admin_pw)
    resp = client.post(f'/admin/api/users/{admin.id}/active', json={'active': False})
    assert resp.status_code == 400
    assert User.query.get(admin.id).is_active is True


def test_users_json_includes_is_active(app, client, db_session):
    admin, admin_pw = _make_user(db_session, 'admin3@example.com', role='admin')
    login_as(client, app, admin, admin_pw)
    resp = client.get('/admin/api/users')
    assert resp.status_code == 200
    rows = resp.get_json()
    assert rows and all('is_active' in r for r in rows)
