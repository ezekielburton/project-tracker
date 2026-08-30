"""Coverage for project_overlay/submissions.py. overlay_submissions itself
(auth + happy path) is covered by test_overlay_history_perf.py; this adds
the draft-card fragment endpoint."""
from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as


def _standard_project(db_session, tag):
    user = User(name='CS Lead', email=f'submissions-test-{tag}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    project = Project(
        name=f'Submissions Test Project {tag}', brief_type='standard',
        cs_lead_id=user.id, created_by_id=user.id, project_status='in_design',
    )
    db_session.add(project)
    db_session.flush()
    return user, project


def test_overlay_submissions_content_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_submissions_content', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_overlay_submissions_content_renders_with_no_draft(app, client, db_session):
    user, project = _standard_project(db_session, 'a')
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay_submissions_content', project_id=project.id, scope='ckv')
    resp = client.get(url)
    assert resp.status_code == 200
