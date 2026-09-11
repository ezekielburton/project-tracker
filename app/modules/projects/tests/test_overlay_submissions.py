"""Coverage for project_overlay/submissions.py. overlay_submissions itself
(auth + happy path) is covered by test_overlay_history_perf.py; this adds
the draft-card fragment endpoint."""
from flask import url_for

from app.modules.core.shared.models import User, Project, ProjectSubmission
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


# ── Start Project gates draft work ─────────────────────────────────────────

def _designer(db_session, tag, role='designer'):
    user = User(name=f'Submissions {tag}', email=f'submissions-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _briefed_project(db_session, tag, owner):
    project = Project(
        name=f'Briefed Project {tag}', brief_type='standard',
        cs_lead_id=owner.id, created_by_id=owner.id, project_status='briefed',
    )
    db_session.add(project)
    db_session.flush()
    return project


def _upload_url(app, project_id):
    with app.test_request_context():
        return url_for('project_overlay.overlay_submissions_upload', project_id=project_id)


def test_a_briefed_project_refuses_draft_work(app, client, db_session):
    designer = _designer(db_session, 'briefed')
    project = _briefed_project(db_session, 'briefed', designer)
    login_as(client, app, designer, 'password123')

    assert client.post(_upload_url(app, project.id)).status_code == 409


def test_a_briefed_project_with_a_draft_already_on_it_still_accepts_work(app, client, db_session):
    """The grandfather clause: work started before the rule stays reachable.
    400 means the gate let it through and only the missing file stopped it."""
    designer = _designer(db_session, 'grandfathered')
    project = _briefed_project(db_session, 'grandfathered', designer)
    db_session.add(ProjectSubmission(
        project_id=project.id, filename='draft', original_filename='draft',
        file_type='draft', uploaded_by_id=designer.id, is_active=True,
        workflow_status='draft',
    ))
    db_session.flush()
    login_as(client, app, designer, 'password123')

    assert client.post(_upload_url(app, project.id)).status_code == 400


def test_a_role_without_manage_drafts_cannot_upload(app, client, db_session):
    """The upload route used to have no capability check at all."""
    owner, project = _standard_project(db_session, 'no-drafts')
    outsider = _designer(db_session, 'finance-outsider', role='finance')
    login_as(client, app, outsider, 'password123')

    assert client.post(_upload_url(app, project.id)).status_code == 403
