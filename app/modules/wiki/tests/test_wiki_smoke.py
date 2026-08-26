"""Smoke tests for the wiki module, using the shared fixtures."""
from flask import url_for


def test_wiki_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('wiki.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_wiki_templates_resolve(app):
    for name in ('wiki/index.html', 'wiki/editor_dashboard.html'):
        assert app.jinja_env.get_template(name) is not None