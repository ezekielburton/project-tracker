"""C3 regression test: table_row()'s single-project decision must always
match what table_rows() (the full view) would show, across the filter
dimensions most likely to drift if reimplemented per-row (status,
urgency, deadline range, team, designers, search)."""
from datetime import date, timedelta

from app.modules.core.shared.models import User, Project, Deliverable, ProjectDesigner
from app.modules.core.shared.testing import login_as
from flask import url_for


def _make_actor(db_session, email):
    user = User(name='C3 Test User', email=email, role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _make_project(db_session, actor, name, **kwargs):
    project = Project(
        name=name, brief_type='standard', project_status=kwargs.pop('project_status', 'briefed'),
        cs_lead_id=actor.id, created_by_id=actor.id, **kwargs,
    )
    db_session.add(project)
    db_session.flush()
    return project


def _table_rows_contains(client, app, project_id, qs):
    with app.test_request_context():
        url = url_for('project_list.table_rows')
    resp = client.get(url + qs)
    assert resp.status_code == 200
    return f'data-project-id="{project_id}"' in resp.get_data(as_text=True)


def _table_row_status(client, app, project_id, qs):
    with app.test_request_context():
        url = url_for('project_list.table_row', project_id=project_id)
    return client.get(url + qs).status_code


def _assert_matches(client, app, project_id, qs):
    in_full = _table_rows_contains(client, app, project_id, qs)
    status = _table_row_status(client, app, project_id, qs)
    if in_full:
        assert status == 200, f'{qs!r}: in full view but table_row returned {status}'
    else:
        assert status == 204, f'{qs!r}: not in full view but table_row returned {status}'


def test_table_row_matches_table_rows_across_filters(app, client, db_session):
    actor = _make_actor(db_session, 'c3test-actor@example.com')
    other_designer = User(name='C3 Designer', email='c3test-designer@example.com', role='designer')
    other_designer.set_password('password123')
    db_session.add(other_designer)
    db_session.flush()

    plain = _make_project(db_session, actor, 'C3 Plain Project')

    team_project = _make_project(db_session, actor, 'C3 Team Project', design_teams_requested='2D')

    designer_project = _make_project(db_session, actor, 'C3 Designer Project')
    db_session.add(ProjectDesigner(project_id=designer_project.id, user_id=other_designer.id, team='2D'))
    db_session.flush()

    deadline_project = _make_project(db_session, actor, 'C3 Deadline Project')
    db_session.add(Deliverable(
        project_id=deadline_project.id, name='C3 Deliverable', teams='2D',
        created_by_id=actor.id, design_deadline=date.today() + timedelta(days=10),
    ))
    db_session.flush()

    search_project = _make_project(db_session, actor, 'Zephyr Unique Search Target')

    login_as(client, app, actor, 'password123')

    from_5 = (date.today() + timedelta(days=5)).isoformat()
    to_15 = (date.today() + timedelta(days=15)).isoformat()
    from_20 = (date.today() + timedelta(days=20)).isoformat()

    cases = [
        (plain, ''),
        (plain, '?status=Briefed'),
        (plain, '?status=On Hold'),
        (plain, '?urgency=normal'),
        (team_project, '?team=2D'),
        (team_project, '?team=3D'),
        (designer_project, f'?designers={other_designer.id}'),
        (designer_project, f'?designers={actor.id}'),
        (deadline_project, '?urgency=normal'),
        (deadline_project, '?urgency=overdue'),
        (deadline_project, f'?next_deadline_from={from_5}&next_deadline_to={to_15}'),
        (deadline_project, f'?next_deadline_from={from_20}'),
        (search_project, '?search=zephyr'),
        (search_project, '?search=nomatch'),
    ]

    for project, qs in cases:
        _assert_matches(client, app, project.id, qs)
