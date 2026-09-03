"""Route-level coverage for the Digital Innovation Performance page
(routes/performance.py): auth, the can_view_di_performance gate, and the
view/period querystring resolution degrading gracefully instead of
500ing. lib/periods.py and lib/snapshots.py (the actual rollup math) have
full unit coverage in test_periods.py/test_snapshots.py — these tests are
about the HTTP layer, the same split test_costs_routes.py uses for the
cost ledger.

Every test that actually renders the page seeds a permanent DiProject
first: default_project()/_sidebar.html's Board link always resolve
against the permanent project in production (seeded by the migration,
un-deletable — see board_data.py::default_project()'s docstring), but
this test DB starts empty, so the sidebar has nothing to link to without
one. Same pattern test_archive_routes.py and test_project_routes.py use
for their own not-project-scoped pages."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject
from app.modules.digital_innovation.tests.test_features_routes import _user


def _permanent_project(db_session):
    project = DiProject(name='OVP', lifecycle='active', is_permanent=True)
    db_session.add(project)
    db_session.flush()
    return project


def test_performance_requires_auth(app, client, db_session):
    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_performance_403s_for_a_designer(app, client, db_session):
    user = _user(db_session, 'a', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen')
    resp = client.get(url)
    assert resp.status_code == 403


def test_performance_happy_path_for_admin(app, client, db_session):
    _permanent_project(db_session)
    user = _user(db_session, 'b', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen')
    resp = client.get(url)

    assert resp.status_code == 200
    assert b'Performance' in resp.data


def test_performance_works_for_management_role(app, client, db_session):
    _permanent_project(db_session)
    user = _user(db_session, 'c', role='management')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen')
    resp = client.get(url)
    assert resp.status_code == 200


def test_performance_defaults_to_the_weekly_view(app, client, db_session):
    _permanent_project(db_session)
    user = _user(db_session, 'd', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen')
    resp = client.get(url)
    body = resp.get_data(as_text=True)
    assert 'di-perf-tab--active">Weekly' in body


def test_performance_month_view_works(app, client, db_session):
    _permanent_project(db_session)
    user = _user(db_session, 'e', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen', view='month')
    resp = client.get(url)
    assert resp.status_code == 200


def test_performance_falls_back_to_week_for_an_unknown_view(app, client, db_session):
    _permanent_project(db_session)
    user = _user(db_session, 'f', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen', view='fortnight')
    resp = client.get(url)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'di-perf-tab--active">Weekly' in body


def test_performance_falls_back_to_the_current_period_for_a_garbage_period_value(app, client, db_session):
    _permanent_project(db_session)
    user = _user(db_session, 'g', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.performance_screen', view='week', period='not-a-real-period')
    resp = client.get(url)
    assert resp.status_code == 200


# ── export_performance ───────────────────────────────────────────────────
# Same shape as test_costs_routes.py's export_cost_ledger coverage — this
# route doesn't render a page, so it needs no _permanent_project() seed.

def test_export_performance_requires_auth(app, client, db_session):
    with app.test_request_context():
        url = url_for('digital_innovation.export_performance')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_export_performance_403s_for_a_designer(app, client, db_session):
    user = _user(db_session, 'h', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.export_performance')
    resp = client.get(url)
    assert resp.status_code == 403


def test_export_performance_returns_an_xlsx_download(app, client, db_session):
    user = _user(db_session, 'i', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.export_performance')
    resp = client.get(url)

    assert resp.status_code == 200
    assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert 'attachment' in resp.headers.get('Content-Disposition', '')


def test_export_performance_honours_the_view_and_period_querystring(app, client, db_session):
    user = _user(db_session, 'j', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.export_performance', view='month', period='2026-09')
    resp = client.get(url)

    assert resp.status_code == 200
    assert 'di_performance_month_2026-09.xlsx' in resp.headers.get('Content-Disposition', '')
