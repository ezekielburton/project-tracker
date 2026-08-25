"""Smoke tests for the client_directory module, using the shared fixtures."""
from flask import url_for


def test_directory_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('client_directory.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_directory_template_resolves(app):
    assert app.jinja_env.get_template('client_directory/index.html') is not None
