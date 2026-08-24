"""Smoke tests for the profile module, using the shared fixtures."""
from flask import url_for


def test_profile_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('profile.view')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_profile_template_resolves(app):
    # The renamed template must resolve through the module's template_folder.
    assert app.jinja_env.get_template('profile/profile.html') is not None