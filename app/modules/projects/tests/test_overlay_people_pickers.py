"""Details page people pickers: Project Owner and Design Lead."""
from flask import url_for

from app.modules.core.shared.models import Project, User
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role, team=None, is_active=True):
    user = User(name=f'Picker {tag}', email=f'picker-{tag}@example.com', role=role,
                team=team, is_active=is_active)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, cs_lead):
    project = Project(name='Picker Project', brief_type='standard',
                      cs_lead_id=cs_lead.id, created_by_id=cs_lead.id,
                      project_status='in_design', design_teams_requested='2D,3D')
    db_session.add(project)
    db_session.flush()
    return project


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def test_set_project_owner_without_permission_is_403(app, client, db_session):
    cs_lead = _user(db_session, 'own-lead', 'cs')
    other_cs = _user(db_session, 'own-other', 'cs')
    owner = _user(db_session, 'own-po', 'project_owner')
    project = _project(db_session, cs_lead)

    login_as(client, app, other_cs, 'password123')
    resp = client.post(_url(app, 'project_overlay.set_project_owner', project_id=project.id),
                       data={'user_id': owner.id})
    assert resp.status_code == 403
    assert db_session.get(Project, project.id).project_owner_id is None
