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
