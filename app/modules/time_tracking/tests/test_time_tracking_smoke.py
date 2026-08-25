"""Smoke tests for the time_tracking module, using the shared fixtures."""
from flask import url_for


def test_time_tracking_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('time_tracking.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_time_tracking_template_resolves(app):
    assert app.jinja_env.get_template('time_tracking/index.html') is not None


def test_logic_exposes_dashboard_contract(app):
    # The dashboard's Average Time card depends on these three symbols living
    # in the module's logic.py. This guards that boundary through the overhaul.
    from app.modules.time_tracking.logic import (
        build_time_tracking_rows,
        compute_project_hours,
        compute_deliverable_hours,
    )
    assert callable(build_time_tracking_rows)
    assert callable(compute_project_hours)
    assert callable(compute_deliverable_hours)
