"""Coverage for project_overlay/flags.py."""
from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as


def _standard_project(db_session, tag):
    user = User(name='CS Lead', email=f'flags-test-{tag}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    project = Project(
        name=f'Flags Test Project {tag}', brief_type='standard',
        cs_lead_id=user.id, created_by_id=user.id, project_status='in_design',
    )
    db_session.add(project)
    db_session.flush()
    return user, project


def test_overlay_flags_history_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_flags_history', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_create_flag_then_appears_in_history(app, client, db_session):
    user, project = _standard_project(db_session, 'a')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        create_url = url_for('project_overlay.overlay_create_flag', project_id=project.id)
    resp = client.post(create_url, json={'flag_type': 'project', 'message': 'Please review the brief.'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    with app.test_request_context():
        history_url = url_for('project_overlay.overlay_flags_history', project_id=project.id)
    resp = client.get(history_url)
    assert resp.status_code == 200
    flags = resp.get_json()['flags']
    assert len(flags) == 1
    assert flags[0]['messages'][0]['message'] == 'Please review the brief.'
