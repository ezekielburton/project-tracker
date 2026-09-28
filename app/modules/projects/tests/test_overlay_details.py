"""Coverage for project_overlay/details.py."""
from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as


def _standard_project(db_session, tag):
    user = User(name='CS Lead', email=f'details-test-{tag}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    project = Project(
        name=f'Details Test Project {tag}', brief_type='standard',
        cs_lead_id=user.id, created_by_id=user.id, project_status='in_design',
    )
    db_session.add(project)
    db_session.flush()
    return user, project


def test_overlay_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_overlay_renders_project(app, client, db_session):
    user, project = _standard_project(db_session, 'a')
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 200
    assert project.name in resp.get_data(as_text=True)


def test_overlay_details_fragment_renders(app, client, db_session):
    user, project = _standard_project(db_session, 'b')
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay_details', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 200


def _nas_url(app, project_id):
    with app.test_request_context():
        return url_for('project_overlay.overlay_nas_folder_link', project_id=project_id)


def _fake_drive(monkeypatch):
    from app.modules.core.shared.services import nas
    monkeypatch.setattr(nas, 'build_drive_folder_url', lambda path: 'https://drive.example/f')


def test_nas_folder_link_refuses_roles_without_the_workspace(app, client, db_session, monkeypatch):
    _fake_drive(monkeypatch)
    _user, project = _standard_project(db_session, 'nas-hse')
    officer = User(name='HSE Officer', email='details-test-nas-officer@example.com', role='hse')
    officer.set_password('password123')
    db_session.add(officer)
    db_session.flush()

    login_as(client, app, officer, 'password123')
    assert client.get(_nas_url(app, project.id)).status_code == 403


def test_nas_folder_link_returns_url(app, client, db_session, monkeypatch):
    _fake_drive(monkeypatch)
    user, project = _standard_project(db_session, 'nas-ok')
    login_as(client, app, user, 'password123')
    resp = client.get(_nas_url(app, project.id))
    assert resp.status_code == 200
    assert resp.get_json()['url'] == 'https://drive.example/f'


def test_nas_folder_link_without_created_at_is_not_a_500(app, client, db_session, monkeypatch):
    _fake_drive(monkeypatch)
    user, project = _standard_project(db_session, 'nas-nodate')
    project.created_at = None
    db_session.flush()
    login_as(client, app, user, 'password123')
    resp = client.get(_nas_url(app, project.id))
    assert resp.status_code == 404
    assert resp.get_json()['success'] is False
