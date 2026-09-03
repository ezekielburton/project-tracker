"""Route-level coverage for the Client Servicing table view (read-only)."""
from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing, ClientServicingScope


def _user(db_session, tag, role='cs'):
    user = User(name='Test User', email=f'cs-route-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_index_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_index_forbidden_for_disallowed_role(app, client, db_session):
    user = _user(db_session, 'a', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    assert resp.status_code == 403


def test_index_allowed_for_project_owner(app, client, db_session):
    """Project Owners are in the allowed-role set alongside
    admin/management/cs — they can view/use the CS sheet."""
    user = _user(db_session, 'a2', role='project_owner')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    assert resp.status_code == 200


def test_index_forbidden_for_finance_role_not_added_yet(app, client, db_session):
    """Finance is meant to be added to the allowed-role set too, but the
    role doesn't exist in the User model yet — access.py has it commented
    out for Ezekiel to uncomment once it does. This test just locks in
    that "not yet" state; it should be updated (or simply deleted, since
    test_index_allowed_for_project_owner's pattern covers it once
    uncommented) the same day that comment gets removed."""
    user = _user(db_session, 'a3', role='finance')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    assert resp.status_code == 403


def test_index_shows_project_and_cs_fields(app, client, db_session):
    user = _user(db_session, 'b', role='cs')
    project = Project(name='Storefront Refresh', cs_lead_id=user.id, created_by_id=user.id, job_number='JOB-1')
    db_session.add(project)
    db_session.flush()
    db_session.add(ClientServicing(project_id=project.id, lpo='LPO-9'))
    db_session.flush()

    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Storefront Refresh' in body
    assert 'JOB-1' in body
    assert 'LPO-9' in body


def test_table_rows_endpoint_returns_fragment(app, client, db_session):
    user = _user(db_session, 'c', role='admin')
    project = Project(name='Kiosk Build', cs_lead_id=user.id, created_by_id=user.id)
    db_session.add(project)
    db_session.flush()

    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('client_servicing.table_rows')
    resp = client.get(url)

    assert resp.status_code == 200
    assert 'Kiosk Build' in resp.get_data(as_text=True)


def test_deactivated_scope_drops_out_of_options_but_still_shows_on_its_row(app, client, db_session):
    """A deactivated scope shouldn't be offered
    for new picks, but a row that already has it should keep showing its
    name — deactivating isn't deleting."""
    user = _user(db_session, 'd', role='cs')
    scope = ClientServicingScope(name='Legacy Scope', active=True)
    db_session.add(scope)
    db_session.flush()
    project = Project(name='Old Scope Project', cs_lead_id=user.id, created_by_id=user.id)
    db_session.add(project)
    db_session.flush()
    db_session.add(ClientServicing(project_id=project.id, scope_id=scope.id))
    scope.active = False
    db_session.flush()

    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('client_servicing.index')
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Legacy Scope' in body  # still shown on the row

    options_start = body.index('__csScopeOptions = ')
    options_end = body.index(';', options_start)
    options_json = body[options_start:options_end]
    assert 'Legacy Scope' not in options_json  # but not offered for a fresh pick
