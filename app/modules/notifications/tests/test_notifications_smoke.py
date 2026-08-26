"""Smoke tests for the notifications module, using the shared fixtures."""
from flask import url_for


def test_poll_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('notifications.poll')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_notifications_endpoints_registered(app):
    rules = {r.endpoint for r in app.url_map.iter_rules()}
    assert 'notifications.poll' in rules
    assert 'notifications.mark_read' in rules