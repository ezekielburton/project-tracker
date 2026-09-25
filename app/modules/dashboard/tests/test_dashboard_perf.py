"""The dashboard's query count must not grow with the number of projects, and its
per-request project cache must never carry data from one request into the next.

The auth check comes first: a login earlier in a file has made later
unauthenticated checks misbehave (see projects_optimization notes)."""
from datetime import date, datetime, timedelta

import pytest
from flask import url_for

from app.modules.core.shared.models import (
    ActivityLog, BriefFlag, BriefFlagMessage, Customer, DecisionFlag, DecisionFlagMessage,
    Deliverable, DeliverableAssignment, Project, ProjectCustomer, ProjectDesigner,
    ProjectPosmChannel, ProjectStatusLog, User,
)
from app.modules.core.shared.testing import count_queries, login_as
from app.modules.dashboard.lib.project_loader import load_scoped_projects, open_decision_flags

PASSWORD = 'password123'


def _user(db_session, email, role, team=None):
    user = User(name=email.split('@')[0], email=email, role=role, team=team)
    user.set_password(PASSWORD)
    db_session.add(user)
    db_session.flush()
    return user


def _cast(db_session, tag):
    """One user per role; every seeded batch reuses them so only the project count grows."""
    return {
        'management': _user(db_session, f'{tag}-mgmt@example.com', 'management'),
        'cs': _user(db_session, f'{tag}-cs@example.com', 'cs'),
        'designer': _user(db_session, f'{tag}-designer@example.com', 'designer', team='2D'),
        'project_owner': _user(db_session, f'{tag}-po@example.com', 'project_owner'),
    }


def _seed_batch(db_session, cast, n):
    """A Standard and a C&CM project carrying every relationship the dashboard reads."""
    cs, designer, mgmt, po = cast['cs'], cast['designer'], cast['management'], cast['project_owner']
    today = date.today()
    common = dict(cs_lead_id=cs.id, created_by_id=cs.id, project_owner_id=po.id,
                  project_status='in_progress', design_teams_requested='2D,3D',
                  execution_date=today + timedelta(days=3))

    standard = Project(name=f'Perf Standard {n}', brief_type='standard', decision_needed=True, **common)
    ccm = Project(name=f'Perf CCM {n}', brief_type='ccm', **common)
    db_session.add_all([standard, ccm])
    db_session.flush()

    customer = Customer(name=f'Perf Customer {n}', region='uae')
    db_session.add(customer)
    db_session.flush()
    pc = ProjectCustomer(project_id=ccm.id, customer_id=customer.id, design_deadline=today - timedelta(days=1))
    db_session.add(pc)
    db_session.flush()

    deliverables = [
        Deliverable(project_id=standard.id, name=f'Std A {n}', teams='2D', created_by_id=cs.id,
                    design_deadline=today + timedelta(days=1)),
        Deliverable(project_id=standard.id, name=f'Std B {n}', teams='2D', created_by_id=cs.id,
                    design_deadline=today + timedelta(days=1)),
        Deliverable(project_id=ccm.id, project_customer_id=pc.id, name=f'CCM A {n}', teams='2D',
                    created_by_id=cs.id, design_deadline=today - timedelta(days=1)),
    ]
    db_session.add_all(deliverables)
    db_session.flush()

    for d in deliverables:
        db_session.add(DeliverableAssignment(deliverable_id=d.id, designer_id=designer.id, team='2D',
                                             assigned_by_id=cs.id))
    for p in (standard, ccm):
        db_session.add(ProjectDesigner(project_id=p.id, user_id=designer.id, team='2D'))
        db_session.add(ProjectStatusLog(project_id=p.id, status='in_progress'))
        db_session.add(ActivityLog(action='update', description='Perf change', entity_type='project',
                                   entity_id=p.id, entity_name=p.name, user_id=cs.id))
    db_session.add(ProjectPosmChannel(project_id=ccm.id, posm_country='uae', posm_customer_id=pc.id,
                                      status='submitted_to_client'))

    brief_flag = BriefFlag(project_id=standard.id, deliverable_id=deliverables[0].id, flag_type='deliverable',
                           created_by_id=designer.id)
    open_flag = DecisionFlag(project_id=standard.id, created_by_id=cs.id, note='Needs a call')
    resolved_flag = DecisionFlag(project_id=ccm.id, created_by_id=cs.id, note='Old call', is_resolved=True,
                                 resolved_at=datetime.utcnow(), resolved_by_id=mgmt.id)
    db_session.add_all([brief_flag, open_flag, resolved_flag])
    db_session.flush()
    db_session.add(BriefFlagMessage(flag_id=brief_flag.id, author_id=cs.id, message='Brief detail'))
    db_session.add(DecisionFlagMessage(flag_id=open_flag.id, author_id=mgmt.id, message='Looking'))
    db_session.flush()


def _dashboard_queries(client, db_session, url):
    """Queries for one cold page load: nothing already loaded from an earlier request."""
    db_session.expire_all()
    with count_queries() as n:
        resp = client.get(url)
    assert resp.status_code == 200
    return n[0]


def test_dashboard_api_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('projects.api_due')
    assert client.get(url).status_code in (302, 401)


@pytest.mark.parametrize('role', ['management', 'cs', 'designer', 'project_owner'])
def test_dashboard_query_count_does_not_scale_with_projects(app, client, db_session, role):
    cast = _cast(db_session, f'perf-{role}')
    _seed_batch(db_session, cast, 1)
    login_as(client, app, cast[role], PASSWORD)
    with app.test_request_context():
        url = url_for('projects.index')

    small = _dashboard_queries(client, db_session, url)
    for n in range(2, 5):
        _seed_batch(db_session, cast, n)
    big = _dashboard_queries(client, db_session, url)

    assert big == small


def test_scoped_projects_are_fresh_each_request(app, db_session):
    cast = _cast(db_session, 'perf-fresh')
    _seed_batch(db_session, cast, 1)
    with app.test_request_context('/dashboard'):
        first = load_scoped_projects(cast['cs'])

    _seed_batch(db_session, cast, 2)
    with app.test_request_context('/dashboard'):
        second = load_scoped_projects(cast['cs'])

    assert len(second) == len(first) + 2


def test_scoped_projects_fetch_once_per_request(app, db_session):
    cast = _cast(db_session, 'perf-once')
    _seed_batch(db_session, cast, 1)
    with app.test_request_context('/dashboard'):
        first = load_scoped_projects(cast['cs'])
        first.clear()
        with count_queries() as n:
            again = load_scoped_projects(cast['cs'])
    assert n[0] == 0
    assert len(again) == 2


def test_scoped_projects_skip_draft_and_finished(app, db_session):
    cast = _cast(db_session, 'perf-scope')
    _seed_batch(db_session, cast, 1)
    cs = cast['cs']
    for status in ('draft', 'approved', 'handed_to_production'):
        db_session.add(Project(name=f'Perf {status}', project_status=status, cs_lead_id=cs.id, created_by_id=cs.id))
    db_session.flush()

    with app.test_request_context('/dashboard'):
        names = sorted(p.name for p in load_scoped_projects(cs))
    assert names == ['Perf CCM 1', 'Perf Standard 1']


def test_open_decision_flags_returns_newest_open_flag(app, db_session):
    cast = _cast(db_session, 'perf-flags')
    cs = cast['cs']
    project = Project(name='Perf Flags', project_status='in_progress', cs_lead_id=cs.id, created_by_id=cs.id)
    db_session.add(project)
    db_session.flush()
    now = datetime.utcnow()
    older = DecisionFlag(project_id=project.id, created_by_id=cs.id, note='older', created_at=now - timedelta(days=2))
    newer = DecisionFlag(project_id=project.id, created_by_id=cs.id, note='newer', created_at=now - timedelta(days=1))
    resolved = DecisionFlag(project_id=project.id, created_by_id=cs.id, note='resolved', created_at=now,
                            is_resolved=True)
    db_session.add_all([older, newer, resolved])
    db_session.flush()

    flags = open_decision_flags([project.id])
    assert flags[project.id].note == 'newer'
    assert open_decision_flags([]) == {}
