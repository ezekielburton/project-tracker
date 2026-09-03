"""Coverage for the Client Servicing field-update endpoint (CS-only fields)."""
import json

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing, ClientServicingScope


def _user(db_session, tag, role='cs'):
    user = User(name='Test User', email=f'cs-edit-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, tag, user):
    project = Project(name=f'Edit Test Project {tag}', cs_lead_id=user.id, created_by_id=user.id)
    db_session.add(project)
    db_session.flush()
    return project


def _patch(client, app, project_id, field, value):
    with app.test_request_context():
        url = url_for('client_servicing.update_field', project_id=project_id)
    return client.patch(url, data=json.dumps({'field': field, 'value': value}), content_type='application/json')


def test_editable_field_saves_and_creates_cs_row(app, client, db_session):
    user = _user(db_session, 'a')
    project = _project(db_session, 'a', user)
    login_as(client, app, user, 'password123')

    resp = _patch(client, app, project.id, 'lpo', 'LPO-42')
    assert resp.status_code == 200
    assert resp.get_json()['value'] == 'LPO-42'

    cs = ClientServicing.query.filter_by(project_id=project.id).first()
    assert cs is not None
    assert cs.lpo == 'LPO-42'


def test_disallowed_field_rejected(app, client, db_session):
    user = _user(db_session, 'b')
    project = _project(db_session, 'b', user)
    login_as(client, app, user, 'password123')

    resp = _patch(client, app, project.id, 'lpo_number_typo_field', 'JOB-99')
    assert resp.status_code == 400
    assert ClientServicing.query.filter_by(project_id=project.id).first() is None


def test_wrong_type_rejected(app, client, db_session):
    user = _user(db_session, 'c')
    project = _project(db_session, 'c', user)
    login_as(client, app, user, 'password123')

    resp = _patch(client, app, project.id, 'cost_to_client', 'not-a-number')
    assert resp.status_code == 400

    resp2 = _patch(client, app, project.id, 'cost_to_client', -5)
    assert resp2.status_code == 400


def test_permission_enforced(app, client, db_session):
    user = _user(db_session, 'd', role='designer')
    project = _project(db_session, 'd', user)
    login_as(client, app, user, 'password123')

    resp = _patch(client, app, project.id, 'lpo', 'LPO-1')
    assert resp.status_code == 403


def test_margin_recomputes_on_cost_edit(app, client, db_session):
    user = _user(db_session, 'e')
    project = _project(db_session, 'e', user)
    login_as(client, app, user, 'password123')

    _patch(client, app, project.id, 'cost_to_client', '100')
    resp = _patch(client, app, project.id, 'inward_cost', '60')

    assert resp.status_code == 200
    assert resp.get_json()['margin_percent'] == 40.0


def test_scope_must_be_active_and_existing(app, client, db_session):
    user = _user(db_session, 'f')
    project = _project(db_session, 'f', user)
    scope = ClientServicingScope(name='Retail Fit-out', active=True)
    inactive_scope = ClientServicingScope(name='Retired Scope', active=False)
    db_session.add_all([scope, inactive_scope])
    db_session.flush()
    login_as(client, app, user, 'password123')

    ok = _patch(client, app, project.id, 'scope_id', scope.id)
    assert ok.status_code == 200
    assert ok.get_json()['value'] == 'Retail Fit-out'

    bad = _patch(client, app, project.id, 'scope_id', inactive_scope.id)
    assert bad.status_code == 400

    missing = _patch(client, app, project.id, 'scope_id', 999999)
    assert missing.status_code == 400
