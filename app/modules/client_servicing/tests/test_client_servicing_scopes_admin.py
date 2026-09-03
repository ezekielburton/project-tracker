"""Coverage for the Scope reference-data endpoints
(app/modules/client_servicing/routes/scopes_admin.py): full CRUD is
admin-only (list/create/rename/deactivate), quick-add is open to the same
cs/management/admin set as the rest of the module."""
import json

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicingScope


def _user(db_session, tag, role='cs'):
    user = User(name=f'Scope Test User {tag}', email=f'cs-scope-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _scope(db_session, tag, active=True):
    scope = ClientServicingScope(name=f'Scope {tag}', active=active)
    db_session.add(scope)
    db_session.flush()
    return scope


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def test_list_requires_admin_not_just_cs_access(app, client, db_session):
    cs_user = _user(db_session, 'a', role='cs')
    login_as(client, app, cs_user, 'password123')

    resp = client.get(_url(app, 'client_servicing.list_scopes'))
    assert resp.status_code == 403


def test_admin_can_list_and_create(app, client, db_session):
    admin = _user(db_session, 'b', role='admin')
    login_as(client, app, admin, 'password123')

    resp = client.post(_url(app, 'client_servicing.create_scope'),
                        data=json.dumps({'name': 'Full Fitout'}), content_type='application/json')
    assert resp.status_code == 200
    scope_id = resp.get_json()['id']

    resp = client.get(_url(app, 'client_servicing.list_scopes'))
    assert resp.status_code == 200
    names = [s['name'] for s in resp.get_json()]
    assert 'Full Fitout' in names

    assert ClientServicingScope.query.get(scope_id).active is True


def test_create_rejects_duplicate_name(app, client, db_session):
    admin = _user(db_session, 'c', role='admin')
    _scope(db_session, 'c-existing')
    login_as(client, app, admin, 'password123')

    resp = client.post(_url(app, 'client_servicing.create_scope'),
                        data=json.dumps({'name': 'Scope c-existing'}), content_type='application/json')
    assert resp.status_code == 409


def test_rename_scope(app, client, db_session):
    admin = _user(db_session, 'd', role='admin')
    scope = _scope(db_session, 'd')
    login_as(client, app, admin, 'password123')

    resp = client.patch(_url(app, 'client_servicing.update_scope', scope_id=scope.id),
                         data=json.dumps({'name': 'Renamed Scope'}), content_type='application/json')
    assert resp.status_code == 200

    db_session.refresh(scope)
    assert scope.name == 'Renamed Scope'


def test_rename_rejects_duplicate_name(app, client, db_session):
    admin = _user(db_session, 'e', role='admin')
    taken = _scope(db_session, 'e-taken')
    scope = _scope(db_session, 'e-mine')
    login_as(client, app, admin, 'password123')

    resp = client.patch(_url(app, 'client_servicing.update_scope', scope_id=scope.id),
                         data=json.dumps({'name': taken.name}), content_type='application/json')
    assert resp.status_code == 409


def test_deactivate_and_reactivate(app, client, db_session):
    admin = _user(db_session, 'f', role='admin')
    scope = _scope(db_session, 'f')
    login_as(client, app, admin, 'password123')

    resp = client.patch(_url(app, 'client_servicing.update_scope', scope_id=scope.id),
                         data=json.dumps({'active': False}), content_type='application/json')
    assert resp.status_code == 200
    db_session.refresh(scope)
    assert scope.active is False

    resp = client.patch(_url(app, 'client_servicing.update_scope', scope_id=scope.id),
                         data=json.dumps({'active': True}), content_type='application/json')
    assert resp.status_code == 200
    db_session.refresh(scope)
    assert scope.active is True


def test_quick_add_available_to_cs_role_not_just_admin(app, client, db_session):
    cs_user = _user(db_session, 'g', role='cs')
    login_as(client, app, cs_user, 'password123')

    resp = client.post(_url(app, 'client_servicing.quick_add_scope'),
                        data=json.dumps({'name': 'Quick Scope'}), content_type='application/json')
    assert resp.status_code == 200
    assert ClientServicingScope.query.filter_by(name='Quick Scope').first() is not None


def test_quick_add_rejects_role_without_cs_access(app, client, db_session):
    designer = _user(db_session, 'h', role='designer')
    login_as(client, app, designer, 'password123')

    resp = client.post(_url(app, 'client_servicing.quick_add_scope'),
                        data=json.dumps({'name': 'Nope Scope'}), content_type='application/json')
    assert resp.status_code == 403


def test_quick_add_is_idempotent_for_existing_active_scope(app, client, db_session):
    management = _user(db_session, 'i', role='management')
    scope = _scope(db_session, 'i')
    login_as(client, app, management, 'password123')

    resp = client.post(_url(app, 'client_servicing.quick_add_scope'),
                        data=json.dumps({'name': scope.name}), content_type='application/json')
    assert resp.status_code == 200
    assert resp.get_json()['id'] == scope.id
    assert ClientServicingScope.query.filter_by(name=scope.name).count() == 1


def test_quick_add_reactivates_a_deactivated_scope(app, client, db_session):
    """Returning an inactive scope's id here without reactivating it would
    be a dead end - edit.py's _parse_scope_id only accepts active scopes,
    so the very next save would fail with "must be a valid scope" right
    after the user just "added" it."""
    cs_user = _user(db_session, 'j', role='cs')
    scope = _scope(db_session, 'j', active=False)
    login_as(client, app, cs_user, 'password123')

    resp = client.post(_url(app, 'client_servicing.quick_add_scope'),
                        data=json.dumps({'name': scope.name}), content_type='application/json')
    assert resp.status_code == 200
    assert resp.get_json()['active'] is True

    db_session.refresh(scope)
    assert scope.active is True
