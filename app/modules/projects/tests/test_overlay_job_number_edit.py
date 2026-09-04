"""Details edit mode — Job Number. Editable on the overlay by the same people
who can edit the other Details fields (admin/management everywhere; this
project's CS lead/secondary CS; this project's owner). The save routes through
services/mutations.save_detail_field, so it gets the same duplicate check,
notification and history entry a job-number edit from the Client Servicing
table does.

Auth check is ordered first — same file-order quirk noted elsewhere (a prior
login_as can make an unauthenticated check 404 instead of redirect).
"""
from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as


def _make_user(db_session, email, role, name='JN User'):
    user = User(name=name, email=email, role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _make_project(db_session, cs_lead, job_number=None):
    project = Project(
        name='Job Number Project', brief_type='standard',
        cs_lead_id=cs_lead.id, created_by_id=cs_lead.id,
        job_number=job_number,
    )
    db_session.add(project)
    db_session.flush()
    return project


def _save(client, app, project_id, value):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_details_save', project_id=project_id)
    return client.post(url, json={'fields': {'job_number': value}, 'edit_snapshot_at': ''})


def test_job_number_save_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_details_save', project_id=1)
    resp = client.post(url, json={'fields': {'job_number': 'J-1'}, 'edit_snapshot_at': ''})
    assert resp.status_code in (302, 401)


def test_admin_can_edit_job_number(app, client, db_session):
    admin = _make_user(db_session, 'jn-admin@example.com', 'admin')
    project = _make_project(db_session, admin, job_number='OLD-1')
    pid = project.id

    login_as(client, app, admin, 'password123')
    resp = _save(client, app, pid, 'NEW-1')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert db_session.get(Project, pid).job_number == 'NEW-1'


def test_project_cs_lead_can_edit_job_number(app, client, db_session):
    # Project-scoped: the project's own CS lead may edit it.
    cs_lead = _make_user(db_session, 'jn-cslead@example.com', 'cs')
    project = _make_project(db_session, cs_lead, job_number='OLD-2')
    pid = project.id

    login_as(client, app, cs_lead, 'password123')
    resp = _save(client, app, pid, 'NEW-2')
    assert resp.status_code == 200
    assert db_session.get(Project, pid).job_number == 'NEW-2'


def test_duplicate_job_number_rejected(app, client, db_session):
    admin = _make_user(db_session, 'jn-dup-admin@example.com', 'admin')
    other = _make_project(db_session, admin, job_number='TAKEN')
    project = _make_project(db_session, admin, job_number='MINE')
    pid = project.id

    login_as(client, app, admin, 'password123')
    resp = _save(client, app, pid, 'TAKEN')
    assert resp.status_code == 400
    # Unchanged after a rejected duplicate.
    assert db_session.get(Project, pid).job_number == 'MINE'


def test_unauthorised_role_cannot_edit_job_number(app, client, db_session):
    # A designer with no stake in this project is not in the edit set.
    admin = _make_user(db_session, 'jn-owner-admin@example.com', 'admin')
    project = _make_project(db_session, admin, job_number='LOCKED')
    pid = project.id

    outsider = _make_user(db_session, 'jn-designer@example.com', 'designer')
    login_as(client, app, outsider, 'password123')
    resp = _save(client, app, pid, 'HACKED')
    assert resp.status_code == 403
    assert db_session.get(Project, pid).job_number == 'LOCKED'
