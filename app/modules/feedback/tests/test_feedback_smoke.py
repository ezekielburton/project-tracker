"""Smoke tests for the feedback module, using the shared fixtures."""
from flask import url_for


def test_feature_requests_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('feedback.feature_requests')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_bug_reports_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('feedback.bug_reports')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_feedback_templates_resolve(app):
    for name in ('feedback/feature_requests.html', 'feedback/bug_reports.html'):
        assert app.jinja_env.get_template(name) is not None
