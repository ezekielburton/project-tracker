"""Regression test: the Deliverables sub-tab used to lazy-load each row's
assignment tags (and the designer behind each) one at a time, so opening
the tab got slower as a project grew — the cause of the "slow switching to
Deliverables" reports. Now eager-loaded in the tab's own query (Standard
via overlay_deliverables, C&CM via _build_ccm_deliverable_sections). These
prove the query count no longer scales with the number of deliverables,
for both brief types, and that the rows still render.

Auth-required checks are ordered before any login-using test on purpose —
same file-order quirk noted in the Group A pass (a prior login_as in the
file made an unauthenticated check 404 instead of redirecting)."""
from app.modules.core.shared.models import (
    User, Project, ProjectCustomer, Customer, Deliverable, DeliverableAssignment,
)
from app.modules.core.shared.testing import login_as, count_queries
from flask import url_for


def _make_actor(db_session, email):
    user = User(name='Deliv Perf User', email=email, role='admin')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _build_standard_project(db_session, actor, deliverable_count):
    project = Project(
        name='Deliv Perf Standard', brief_type='standard',
        cs_lead_id=actor.id, created_by_id=actor.id,
    )
    db_session.add(project)
    db_session.flush()

    for i in range(deliverable_count):
        designer = User(name=f'DP Designer {i}', email=f'dpdesigner{deliverable_count}-{i}@example.com', role='designer', team='2D')
        designer.set_password('password123')
        db_session.add(designer)
        db_session.flush()

        d = Deliverable(project_id=project.id, name=f'Deliverable {i+1}', teams='2D', created_by_id=actor.id)
        db_session.add(d)
        db_session.flush()

        db_session.add(DeliverableAssignment(
            deliverable_id=d.id, designer_id=designer.id, team='2D', assigned_by_id=actor.id,
        ))

    db_session.flush()
    return project


def _build_ccm_project(db_session, actor, deliverable_count):
    customer = Customer(name=f'DP Customer {deliverable_count}', region='uae')
    db_session.add(customer)
    db_session.flush()

    project = Project(
        name='Deliv Perf CCM', brief_type='ccm',
        cs_lead_id=actor.id, created_by_id=actor.id,
    )
    db_session.add(project)
    db_session.flush()

    pc = ProjectCustomer(project_id=project.id, customer_id=customer.id)
    db_session.add(pc)
    db_session.flush()

    for i in range(deliverable_count):
        designer = User(name=f'DP CCM Designer {i}', email=f'dpccmdesigner{deliverable_count}-{i}@example.com', role='designer', team='2D')
        designer.set_password('password123')
        db_session.add(designer)
        db_session.flush()

        d = Deliverable(project_id=project.id, project_customer_id=pc.id, name=f'CCM Deliverable {i+1}', teams='2D', created_by_id=actor.id)
        db_session.add(d)
        db_session.flush()

        db_session.add(DeliverableAssignment(
            deliverable_id=d.id, designer_id=designer.id, team='2D', assigned_by_id=actor.id,
        ))

    db_session.flush()
    return project


def test_deliverables_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_deliverables', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_standard_deliverables_render(app, client, db_session):
    actor = _make_actor(db_session, 'dp-std-render@example.com')
    project = _build_standard_project(db_session, actor, deliverable_count=3)

    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay_deliverables', project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for i in range(3):
        assert f'Deliverable {i+1}' in body


def test_standard_query_count_does_not_scale_with_deliverables(app, client, db_session):
    actor_small = _make_actor(db_session, 'dp-std-small@example.com')
    project_small = _build_standard_project(db_session, actor_small, deliverable_count=2)
    login_as(client, app, actor_small, 'password123')
    with app.test_request_context():
        url_small = url_for('project_overlay.overlay_deliverables', project_id=project_small.id)
    with count_queries() as small_count:
        resp = client.get(url_small)
    assert resp.status_code == 200

    actor_big = _make_actor(db_session, 'dp-std-big@example.com')
    project_big = _build_standard_project(db_session, actor_big, deliverable_count=6)
    login_as(client, app, actor_big, 'password123')
    with app.test_request_context():
        url_big = url_for('project_overlay.overlay_deliverables', project_id=project_big.id)
    with count_queries() as big_count:
        resp = client.get(url_big)
    assert resp.status_code == 200

    assert big_count[0] == small_count[0]


def test_ccm_query_count_does_not_scale_with_deliverables(app, client, db_session):
    actor_small = _make_actor(db_session, 'dp-ccm-small@example.com')
    project_small = _build_ccm_project(db_session, actor_small, deliverable_count=2)
    login_as(client, app, actor_small, 'password123')
    with app.test_request_context():
        url_small = url_for('project_overlay.overlay_deliverables', project_id=project_small.id)
    with count_queries() as small_count:
        resp = client.get(url_small)
    assert resp.status_code == 200

    actor_big = _make_actor(db_session, 'dp-ccm-big@example.com')
    project_big = _build_ccm_project(db_session, actor_big, deliverable_count=6)
    login_as(client, app, actor_big, 'password123')
    with app.test_request_context():
        url_big = url_for('project_overlay.overlay_deliverables', project_id=project_big.id)
    with count_queries() as big_count:
        resp = client.get(url_big)
    assert resp.status_code == 200

    assert big_count[0] == small_count[0]
