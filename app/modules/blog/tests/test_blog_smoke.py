"""Smoke tests for the blog module, using the shared fixtures."""
from flask import url_for


def test_blog_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('blog.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_blog_templates_resolve(app):
    for name in ('blog/index.html', 'blog/editor.html', 'blog/v12_update.html'):
        assert app.jinja_env.get_template(name) is not None
