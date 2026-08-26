"""Smoke test for the first-login account wizard (part of the profile module)."""
from flask import url_for


def test_wizard_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('wizard.complete')
    resp = client.post(url)
    assert resp.status_code in (302, 401)
