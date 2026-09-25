"""Coverage for project_overlay/deliverables.py."""
from flask import url_for

from app.modules.core.shared.models import User, Project, Deliverable
from app.modules.core.shared.testing import login_as


def _project_with_deliverable(db_session, tag):
    user = User(name='CS Lead', email=f'deliv-test-{tag}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    project = Project(
        name=f'Deliverables Test Project {tag}', brief_type='standard',
        cs_lead_id=user.id, created_by_id=user.id, project_status='in_design',
    )
    db_session.add(project)
    db_session.flush()
    deliverable = Deliverable(project_id=project.id, name=f'Deliverable {tag}', created_by_id=user.id)
    db_session.add(deliverable)
    db_session.flush()
    return user, project, deliverable


def test_overlay_deliverables_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_deliverables', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_overlay_deliverables_renders_standard(app, client, db_session):
    user, project, deliverable = _project_with_deliverable(db_session, 'a')
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay_deliverables', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 200
    assert deliverable.name in resp.get_data(as_text=True)


def test_save_new_type_lands_on_the_real_customer(app, client, db_session):
    """The row sends the project_customers link id; the catalog must key on customers.id."""
    from app.modules.core.shared.models import Client, Customer, ProjectCustomer, DeliverableType

    user, project, _ = _project_with_deliverable(db_session, 'ct')
    brand = Client(name='Type Test Client', created_by_id=user.id)
    db_session.add(brand)
    db_session.flush()
    project.client_id = brand.id
    # Several customers but one link row, so the two id sequences drift
    # apart and a mix-up between them cannot pass by coincidence.
    fillers = [Customer(name=f'Filler {i}', region='UAE') for i in range(3)]
    customer = Customer(name='Target', region='UAE')
    db_session.add_all(fillers + [customer])
    db_session.flush()
    link = ProjectCustomer(project_id=project.id, customer_id=customer.id)
    db_session.add(link)
    db_session.flush()
    assert link.id != customer.id

    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.save_standard_deliverables', project_id=project.id)
    resp = client.post(url, json={'deliverables': [
        {'project_customer_id': link.id, 'new_type_name': 'Roll up banner', 'teams': ['2D']},
    ]})
    assert resp.status_code == 200

    created = DeliverableType.query.filter_by(name='Roll up banner').one()
    assert created.customer_id == customer.id
    saved = Deliverable.query.filter_by(project_id=project.id, name='Roll up banner').one()
    assert saved.project_customer_id == link.id
    assert saved.deliverable_type_id == created.id
