"""Details edit mode — 'Teams Required' (design_teams_requested) can be added
to and removed from after the brief. Dropping a team that has a Design Lead
also clears that lead (per Ezekiel). These cover the server side of that:
add persists (canonically ordered), remove persists and deletes the dropped
team's ProjectDesigner, and an unknown team is rejected.

Auth check is ordered first — same file-order quirk noted in the Group A perf
pass (a prior login_as made an unauthenticated check 404 instead of redirect).
"""
from app.modules.core.shared.models import (
    User, Project, ProjectDesigner,
)
from app.modules.core.shared.testing import login_as
from flask import url_for


def _make_admin(db_session, email):
    user = User(name='Teams Edit Admin', email=email, role='admin')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _make_project(db_session, actor, teams, email_designer=None, lead_team=None):
    project = Project(
        name='Teams Edit Project', brief_type='standard',
        cs_lead_id=actor.id, created_by_id=actor.id,
        design_teams_requested=teams,
    )
    db_session.add(project)
    db_session.flush()
    if lead_team and email_designer:
        designer = User(name='Lead Person', email=email_designer, role='designer', team=lead_team)
        designer.set_password('password123')
        db_session.add(designer)
        db_session.flush()
        db_session.add(ProjectDesigner(project_id=project.id, user_id=designer.id, team=lead_team))
        db_session.flush()
    return project


def _save(client, app, project_id, teams_csv):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_details_save', project_id=project_id)
    return client.post(url, json={'fields': {'design_teams_requested': teams_csv}, 'edit_snapshot_at': ''})


def test_details_save_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_details_save', project_id=1)
    resp = client.post(url, json={'fields': {}, 'edit_snapshot_at': ''})
    assert resp.status_code in (302, 401)


def test_add_team_persists_canonically_ordered(app, client, db_session):
    actor = _make_admin(db_session, 'teams-add@example.com')
    project = _make_project(db_session, actor, '2D')
    pid = project.id

    login_as(client, app, actor, 'password123')
    # Deliberately out of order — should be stored canonically (2D,3D,Technical).
    resp = _save(client, app, pid, 'Technical,2D')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    assert db_session.get(Project, pid).design_teams_requested == '2D,Technical'


def test_remove_team_clears_its_lead(app, client, db_session):
    actor = _make_admin(db_session, 'teams-remove@example.com')
    project = _make_project(
        db_session, actor, '2D,3D',
        email_designer='teams-remove-lead@example.com', lead_team='3D',
    )
    pid = project.id
    assert ProjectDesigner.query.filter_by(project_id=pid, team='3D').first() is not None

    login_as(client, app, actor, 'password123')
    resp = _save(client, app, pid, '2D')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    assert db_session.get(Project, pid).design_teams_requested == '2D'
    # Dropped team's Design Lead is gone; the kept team is untouched.
    assert ProjectDesigner.query.filter_by(project_id=pid, team='3D').first() is None


def test_unknown_team_rejected(app, client, db_session):
    actor = _make_admin(db_session, 'teams-bad@example.com')
    project = _make_project(db_session, actor, '2D')
    pid = project.id

    login_as(client, app, actor, 'password123')
    resp = _save(client, app, pid, '2D,Marketing')
    assert resp.status_code == 400
    # Unchanged.
    assert db_session.get(Project, pid).design_teams_requested == '2D'
