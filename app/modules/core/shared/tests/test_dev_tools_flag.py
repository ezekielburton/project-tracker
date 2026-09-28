"""The dev-only Wipe Projects UI follows DEV_TOOLS_ENABLED, the same flag
the wipe route checks, so it never renders where the route would 403."""
import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


def test_dev_tools_global_follows_the_config_flag(app):
    assert app.jinja_env.globals['dev_tools_enabled'] is bool(app.config.get('DEV_TOOLS_ENABLED'))


def test_wipe_ui_is_hidden_when_dev_tools_are_off(app, client, db_session):
    if app.config.get('DEV_TOOLS_ENABLED'):
        pytest.skip('DEV_TOOLS_ENABLED is set in this environment')
    admin = User(name='Dev Tools Admin', email='dev-tools-admin@example.com', role='admin')
    admin.set_password('password123')
    db_session.add(admin)
    db_session.flush()
    login_as(client, app, admin, 'password123')

    with app.test_request_context():
        page_url = url_for('auth.admin_users')
        wipe_url = url_for('admin.dev_wipe_projects')
    html = client.get(page_url).get_data(as_text=True)
    assert 'id="wipe-modal"' not in html
    assert 'openWipeModal()' not in html
    assert client.post(wipe_url).status_code == 403
