"""Smoke tests for the file_templates module, using the shared fixtures."""
from flask import url_for


def test_file_templates_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('file_templates.index')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_file_templates_template_resolves(app):
    assert app.jinja_env.get_template('file_templates/index.html') is not None


def test_upload_folder_anchored_to_app_root(app):
    import os
    from app.modules.core.shared.lib.paths import template_upload_folder
    with app.app_context():
        assert template_upload_folder() == os.path.join(app.root_path, 'file_templates')
