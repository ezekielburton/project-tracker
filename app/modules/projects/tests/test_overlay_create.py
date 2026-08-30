"""Coverage for project_overlay/create.py."""
from flask import url_for

from app.modules.core.shared.models import User, Scope
from app.modules.core.shared.testing import login_as


def _cs_user(db_session, tag):
    user = User(name='CS Lead', email=f'create-test-{tag}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.add(Scope(name=f'Scope {tag}', active=True))
    db_session.flush()
    return user


def test_overlay_create_shell_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_create_shell', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_overlay_create_draft_then_shell_renders(app, client, db_session):
    user = _cs_user(db_session, 'a')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        create_url = url_for('project_overlay.overlay_create_draft')
    resp = client.post(create_url, json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    project_id = body['project_id']

    with app.test_request_context():
        shell_url = url_for('project_overlay.overlay_create_shell', project_id=project_id)
    resp = client.get(shell_url)
    assert resp.status_code == 200
    assert 'Untitled Draft' in resp.get_data(as_text=True)
