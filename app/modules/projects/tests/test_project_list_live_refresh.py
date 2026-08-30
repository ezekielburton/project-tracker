"""Group C regression tests: task #55's targeted single-row SSE refresh
(table_row()) and the _fetch_all_view_rows() safety cap."""
import app.modules.projects.routes.project_list as project_list_module
from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from flask import url_for


def _make_actor(db_session, email):
    user = User(name='Live Refresh Test User', email=email, role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _make_project(db_session, actor, name, status='briefed'):
    project = Project(
        name=name, brief_type='standard', project_status=status,
        cs_lead_id=actor.id, created_by_id=actor.id,
    )
    db_session.add(project)
    db_session.flush()
    return project


def test_table_row_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_list.table_row', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_table_row_returns_row_for_visible_project(app, client, db_session):
    actor = _make_actor(db_session, 'c1test-visible@example.com')
    project = _make_project(db_session, actor, 'C1 Visible Project')

    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_list.table_row', project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert f'data-project-id="{project.id}"' in body
    assert 'C1 Visible Project' in body


def test_table_row_returns_204_outside_current_view(app, client, db_session):
    actor = _make_actor(db_session, 'c1test-owner@example.com')
    other = _make_actor(db_session, 'c1test-other@example.com')
    other_project = _make_project(db_session, other, 'C1 Other Persons Project')

    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_list.table_row', project_id=other_project.id)
    resp = client.get(url)

    assert resp.status_code == 204


def test_table_row_returns_204_for_unknown_project(app, client, db_session):
    actor = _make_actor(db_session, 'c1test-unknown@example.com')
    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_list.table_row', project_id=999999999)
    resp = client.get(url)

    assert resp.status_code == 204


def test_view_row_cap_truncates_and_flags(app, client, db_session, monkeypatch):
    monkeypatch.setattr(project_list_module, '_VIEW_ROW_CAP', 2)

    actor = _make_actor(db_session, 'c2test-cap@example.com')
    for i in range(3):
        _make_project(db_session, actor, f'C2 Cap Project {i}')

    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_list.index')
    resp = client.get(url)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'Showing 2 of 3 items' in body
    assert 'more than 2 projects' in body
    assert 'first 2 are shown' in body


def test_view_row_cap_not_shown_when_under_cap(app, client, db_session, monkeypatch):
    monkeypatch.setattr(project_list_module, '_VIEW_ROW_CAP', 500)

    actor = _make_actor(db_session, 'c2test-nocap@example.com')
    _make_project(db_session, actor, 'C2 No Cap Project')

    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_list.index')
    resp = client.get(url)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'filter-panel-cap-warning' not in body
