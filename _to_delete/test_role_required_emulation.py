"""role_required and admin_required resolve the emulated user, so an admin
viewing as a lower role is held to that role's access."""
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role):
    u = User(name=f'RRE {tag}', email=f'rre-{tag}@example.com', role=role)
    u.set_password('password123')
    db_session.add(u); db_session.flush()
    return u


def _emulate(client, target):
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = target.id


def _url(app, endpoint, **kw):
    with app.test_request_context():
        return url_for(endpoint, **kw)


def test_role_required_follows_emulated_user(app, client, db_session):
    admin = _user(db_session, 'a', 'admin')
    designer = _user(db_session, 'd', 'designer')
    login_as(client, app, admin, 'password123')
    url = _url(app, 'auth.register')  # role_required('admin')

    assert client.get(url).status_code != 403          # real admin passes
    _emulate(client, designer)
    assert client.get(url).status_code == 403          # emulating a designer is blocked
    with client.session_transaction() as sess:
        sess.pop('emulating_user_id', None)
    assert client.get(url).status_code != 403          # exit restores access


def test_role_required_blocks_a_real_designer(app, client, db_session):
    designer = _user(db_session, 'd2', 'designer')
    login_as(client, app, designer, 'password123')
    assert client.get(_url(app, 'auth.register')).status_code == 403


def test_admin_required_follows_emulated_user(app, client, db_session):
    admin = _user(db_session, 'a3', 'admin')
    designer = _user(db_session, 'd3', 'designer')
    login_as(client, app, admin, 'password123')
    url = _url(app, 'admin.list_users')  # @admin_required

    assert client.get(url).status_code != 403
    _emulate(client, designer)
    assert client.get(url).status_code == 403
