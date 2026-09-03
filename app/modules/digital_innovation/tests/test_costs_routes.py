"""Route-level coverage for the Digital Innovation Cost breakdown modal
(routes/costs.py): auth, the can_view_di_performance gate (shared by view/add/delete), validation turning into 400s,
and the Excel export. lib/costs.py (the business logic) already has full
unit coverage in test_costs_lib.py — these tests are about the HTTP
layer, the same split test_feature_steps_routes.py uses for step_engine."""
import datetime

from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject, DiSetting, DiCostEntry
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.tests.test_features_routes import _user


def _project(db_session, tag, client_charge=None):
    project = DiProject(name=f'Test DI Project {tag}', client_charge=client_charge)
    db_session.add(project)
    db_session.flush()
    return project


def _settings(db_session, rate=100.0):
    settings = DiSetting(dev_hourly_rate=rate, currency='AED')
    db_session.add(settings)
    db_session.flush()
    return settings


# ── view ───────────────────────────────────────────────────────────────────

def test_cost_breakdown_requires_auth(app, client, db_session):
    project = _project(db_session, 'a')
    with app.test_request_context():
        url = url_for('digital_innovation.cost_breakdown', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_cost_breakdown_403s_for_a_designer(app, client, db_session):
    project = _project(db_session, 'b')
    user = _user(db_session, 'b', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.cost_breakdown', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 403


def test_cost_breakdown_happy_path_for_admin(app, client, db_session):
    _settings(db_session, rate=100.0)
    project = _project(db_session, 'c')
    feature = engine.create_feature(project, 'Homepage redesign')
    from app.modules.digital_innovation.lib import costs
    costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'dev_time', hours=2, feature=feature)
    db_session.commit()
    user = _user(db_session, 'c', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.cost_breakdown', project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Cost breakdown' in body
    assert 'Homepage redesign' in body


def test_cost_breakdown_works_for_management_role(app, client, db_session):
    project = _project(db_session, 'd')
    user = _user(db_session, 'd', role='management')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.cost_breakdown', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 200


def test_cost_breakdown_works_for_a_closed_project(app, client, db_session):
    # Deliberately no lifecycle filter — a closed project's cost history
    # is still reviewable.
    project = DiProject(name='Closed project', lifecycle='closed')
    db_session.add(project)
    db_session.flush()
    user = _user(db_session, 'e', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.cost_breakdown', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 200


def test_cost_breakdown_404s_for_an_unknown_project(app, client, db_session):
    user = _user(db_session, 'f', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.cost_breakdown', project_id=999999)
    resp = client.get(url)
    assert resp.status_code == 404


# ── add ───────────────────────────────────────────────────────────────

def test_add_cost_entry_requires_auth(app, client, db_session):
    project = _project(db_session, 'g')
    with app.test_request_context():
        url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(url, json={'type': 'claude', 'date': '2026-08-01', 'amount': 10})
    assert resp.status_code in (302, 401)


def test_add_cost_entry_403s_for_a_designer(app, client, db_session):
    project = _project(db_session, 'h')
    user = _user(db_session, 'h', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(url, json={'type': 'claude', 'date': '2026-08-01', 'amount': 10})
    assert resp.status_code == 403


def test_add_cost_entry_dev_time_happy_path_computes_amount(app, client, db_session):
    _settings(db_session, rate=100.0)
    project = _project(db_session, 'i')
    feature = engine.create_feature(project, 'New thing')
    db_session.commit()
    user = _user(db_session, 'i', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(url, json={
        'type': 'dev_time', 'date': '2026-08-01', 'hours': 2.5, 'feature_id': feature.id,
    })
    assert resp.status_code == 200

    entry = DiCostEntry.query.filter_by(di_project_id=project.id).first()
    assert entry.amount == 250.0
    assert entry.di_feature_id == feature.id


def test_add_cost_entry_claude_happy_path(app, client, db_session):
    project = _project(db_session, 'j')
    user = _user(db_session, 'j', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(url, json={
        'type': 'claude', 'date': '2026-08-01', 'amount': 42, 'description': 'API credits',
    })
    assert resp.status_code == 200

    entry = DiCostEntry.query.filter_by(di_project_id=project.id).first()
    assert entry.amount == 42
    assert entry.description == 'API credits'


def test_add_cost_entry_dev_time_400s_without_a_feature(app, client, db_session):
    project = _project(db_session, 'k')
    user = _user(db_session, 'k', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(url, json={'type': 'dev_time', 'date': '2026-08-01', 'hours': 2})
    assert resp.status_code == 400


def test_add_cost_entry_400s_for_a_bad_date(app, client, db_session):
    project = _project(db_session, 'l')
    user = _user(db_session, 'l', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(url, json={'type': 'claude', 'date': 'not-a-date', 'amount': 10})
    assert resp.status_code == 400


def test_add_cost_entry_400s_for_a_zero_amount(app, client, db_session):
    project = _project(db_session, 'm')
    user = _user(db_session, 'm', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_cost_entry_route', project_id=project.id)
    resp = client.post(url, json={'type': 'claude', 'date': '2026-08-01', 'amount': 0})
    assert resp.status_code == 400


# ── delete ──────────────────────────────────────────────────────────────

def test_delete_cost_entry_happy_path(app, client, db_session):
    from app.modules.digital_innovation.lib import costs
    project = _project(db_session, 'n')
    entry = costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'hardware', amount=99)
    db_session.commit()
    user = _user(db_session, 'n', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_cost_entry_route', entry_id=entry.id)
    resp = client.delete(url)
    assert resp.status_code == 200
    assert DiCostEntry.query.get(entry.id) is None


def test_delete_cost_entry_403s_for_a_designer(app, client, db_session):
    from app.modules.digital_innovation.lib import costs
    project = _project(db_session, 'o')
    entry = costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'hardware', amount=99)
    db_session.commit()
    user = _user(db_session, 'o', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_cost_entry_route', entry_id=entry.id)
    resp = client.delete(url)
    assert resp.status_code == 403
    assert DiCostEntry.query.get(entry.id) is not None


def test_delete_cost_entry_404s_for_an_unknown_entry(app, client, db_session):
    user = _user(db_session, 'p', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_cost_entry_route', entry_id=999999)
    resp = client.delete(url)
    assert resp.status_code == 404


# ── export ──────────────────────────────────────────────────────────────

def test_export_cost_ledger_requires_auth(app, client, db_session):
    project = _project(db_session, 'q')
    with app.test_request_context():
        url = url_for('digital_innovation.export_cost_ledger', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_export_cost_ledger_403s_for_a_designer(app, client, db_session):
    project = _project(db_session, 'r')
    user = _user(db_session, 'r', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.export_cost_ledger', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 403


def test_export_cost_ledger_returns_an_xlsx_download(app, client, db_session):
    from app.modules.digital_innovation.lib import costs
    project = _project(db_session, 's')
    costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'hardware', amount=99)
    db_session.commit()
    user = _user(db_session, 's', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.export_cost_ledger', project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 200
    assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert 'attachment' in resp.headers.get('Content-Disposition', '')
