"""Smoke tests for the dashboard module, using the shared fixtures."""
from flask import url_for


def test_dashboard_requires_auth(app, client):
    # The dashboard blueprint is historically named 'projects'.
    with app.test_request_context():
        url = url_for('projects.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_dashboard_templates_resolve(app):
    for name in ('dashboard.html', 'dashboard_cs.html', 'dashboard_leadership.html',
                 'dashboard/cards/stat_active.html', 'dashboard/_dashboard_macros.html'):
        assert app.jinja_env.get_template(name) is not None


def test_dashboard_logic_importable(app):
    from app.modules.dashboard.lib.dashboard_logic import (
        get_project_rag, compute_clashes, needs_client_approval, guidance_for_viewer,
    )
    assert callable(get_project_rag)
    assert callable(needs_client_approval)
