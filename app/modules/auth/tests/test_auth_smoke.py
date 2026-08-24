"""Smoke tests for the auth module, using the shared fixtures."""
from flask import url_for


def test_login_page_renders(app, client):
    with app.test_request_context():
        url = url_for('auth.login')
    resp = client.get(url)
    assert resp.status_code == 200
    assert b'<form' in resp.data


def test_account_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('auth.account')
    resp = client.get(url)
    # login_required redirects an unauthenticated request to the login view.
    assert resp.status_code in (302, 401)