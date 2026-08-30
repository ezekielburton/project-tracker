"""Group A2 regression test: project-row expand used to lazy-load each
deliverable's disciplines and each discipline's designer one at a time.
Now eager-loaded in the expand query itself. This proves the query count
no longer grows with the number of deliverables, for both the Standard
project path (expand) and the C&CM per-customer path (expand_customer)."""
from app.modules.core.shared.models import (
    User, Project, ProjectCustomer, Customer, Deliverable, DeliverableAssignment,
)
from app.modules.core.shared.testing import login_as, count_queries
from flask import url_for


def _make_actor(db_session, email):
    user = User(name='List Test User', email=email, role='admin')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _build_standard_project(db_session, actor, deliverable_count):
    project = Project(
        name='A2 Test Project', brief_type='standard',
        cs_lead_id=actor.id, created_by_id=actor.id,
    )
    db_session.add(project)
    db_session.flush()

    for i in range(deliverable_count):
        designer = User(name=f'Designer {i}', email=f'a2designer{deliverable_count}-{i}@example.com', role='designer')
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
    customer = Customer(name=f'A2 Test Customer {deliverable_count}', region='UAE')
    db_session.add(customer)
    db_session.flush()

    project = Project(
        name='A2 CCM Test Project', brief_type='ccm',
        cs_lead_id=actor.id, created_by_id=actor.id,
    )
    db_session.add(project)
    db_session.flush()

    pc = ProjectCustomer(project_id=project.id, customer_id=customer.id)
    db_session.add(pc)
    db_session.flush()

    for i in range(deliverable_count):
        designer = User(name=f'CCM Designer {i}', email=f'a2ccmdesigner{deliverable_count}-{i}@example.com', role='designer')
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
    return project, pc


def test_expand_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_list.expand', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)

def test_expand_customer_requires_auth(app, client, db_session):
    from sqlalchemy import func
    max_id = db_session.query(func.max(ProjectCustomer.id)).scalar() or 0
    with app.test_request_context():
        url = url_for('project_list.expand_customer', project_customer_id=max_id + 1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_expand_renders_deliverables_and_designers(app, client, db_session):
    actor = _make_actor(db_session, 'a2test-render@example.com')
    project = _build_standard_project(db_session, actor, deliverable_count=3)

    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_list.expand', project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for i in range(3):
        assert f'Deliverable {i+1}' in body
        assert f'Designer {i}' in body


def test_expand_query_count_does_not_scale_with_deliverables(app, client, db_session):
    actor_small = _make_actor(db_session, 'a2test-small@example.com')
    project_small = _build_standard_project(db_session, actor_small, deliverable_count=2)
    login_as(client, app, actor_small, 'password123')
    with app.test_request_context():
        url_small = url_for('project_list.expand', project_id=project_small.id)
    with count_queries() as small_count:
        resp = client.get(url_small)
    assert resp.status_code == 200

    actor_big = _make_actor(db_session, 'a2test-big@example.com')
    project_big = _build_standard_project(db_session, actor_big, deliverable_count=6)
    login_as(client, app, actor_big, 'password123')
    with app.test_request_context():
        url_big = url_for('project_list.expand', project_id=project_big.id)
    with count_queries() as big_count:
        resp = client.get(url_big)
    assert resp.status_code == 200

    assert big_count[0] == small_count[0]


def test_expand_customer_renders_deliverables_and_designers(app, client, db_session):
    actor = _make_actor(db_session, 'a2test-ccm-render@example.com')
    project, pc = _build_ccm_project(db_session, actor, deliverable_count=3)

    login_as(client, app, actor, 'password123')
    with app.test_request_context():
        url = url_for('project_list.expand_customer', project_customer_id=pc.id)
    resp = client.get(url)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for i in range(3):
        assert f'CCM Deliverable {i+1}' in body
        assert f'CCM Designer {i}' in body


def test_expand_customer_query_count_does_not_scale_with_deliverables(app, client, db_session):
    actor_small = _make_actor(db_session, 'a2test-ccm-small@example.com')
    _, pc_small = _build_ccm_project(db_session, actor_small, deliverable_count=2)
    login_as(client, app, actor_small, 'password123')
    with app.test_request_context():
        url_small = url_for('project_list.expand_customer', project_customer_id=pc_small.id)
    with count_queries() as small_count:
        resp = client.get(url_small)
    assert resp.status_code == 200

    actor_big = _make_actor(db_session, 'a2test-ccm-big@example.com')
    _, pc_big = _build_ccm_project(db_session, actor_big, deliverable_count=6)
    login_as(client, app, actor_big, 'password123')
    with app.test_request_context():
        url_big = url_for('project_list.expand_customer', project_customer_id=pc_big.id)
    with count_queries() as big_count:
        resp = client.get(url_big)
    assert resp.status_code == 200

    assert big_count[0] == small_count[0]