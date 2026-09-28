"""Details edit: Job Number. Who may edit it and the duplicate check
(both via services/mutations.save_detail_field).

The auth test stays first: after a login_as it would 404 instead of redirect.
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


def test_job_number_not_saved_when_another_field_is_invalid(app, client, db_session):
    # All-or-nothing: a bad field alongside a new job number saves neither.
    admin = _make_user(db_session, 'jn-atomic-admin@example.com', 'admin')
    project = _make_project(db_session, admin, job_number='BEFORE')
    pid = project.id

    login_as(client, app, admin, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay_details_save', project_id=pid)
    for bad in ({'execution_date': 'not-a-date'}, {'design_teams_requested': 'Puppetry'}):
        resp = client.post(url, json={
            'fields': {'job_number': 'AFTER', 'client_expectation': 'changed', **bad},
            'edit_snapshot_at': '',
        })
        assert resp.status_code == 400, bad
        db_session.expire_all()
        saved = db_session.get(Project, pid)
        assert saved.job_number == 'BEFORE'
        assert saved.client_expectation is None


def test_job_number_and_fields_save_together(app, client, db_session):
    admin = _make_user(db_session, 'jn-both-admin@example.com', 'admin')
    project = _make_project(db_session, admin, job_number='B-1')
    pid = project.id

    login_as(client, app, admin, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay_details_save', project_id=pid)
    resp = client.post(url, json={
        'fields': {'job_number': 'B-2', 'client_expectation': 'bold'},
        'edit_snapshot_at': '',
    })
    assert resp.status_code == 200
    assert set(resp.get_json()['changes']) == {'job_number', 'client_expectation'}
    db_session.expire_all()
    saved = db_session.get(Project, pid)
    assert (saved.job_number, saved.client_expectation) == ('B-2', 'bold')
