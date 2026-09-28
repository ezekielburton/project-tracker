"""delete_client removes the client's contacts, and refuses (400) a client
still used by projects or deliverable types."""
from flask import url_for

from app.modules.core.shared.models import Client, Contact, Customer, DeliverableType, Project, User
from app.modules.core.shared.testing import login_as


def _admin(db_session):
    user = User(name='Client Deleter', email='client-deleter@example.com', role='admin')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _client(db_session, admin, name):
    client = Client(name=name, created_by_id=admin.id)
    db_session.add(client)
    db_session.flush()
    return client


def _contact(db_session, client):
    contact = Contact(name='Spoc Person', client_id=client.id)
    db_session.add(contact)
    db_session.flush()
    return contact


def _delete(app, client, client_id):
    with app.test_request_context():
        url = url_for('admin.delete_client', client_id=client_id)
    return client.delete(url)


def test_deleting_a_client_with_contacts_removes_both(app, client, db_session):
    admin = _admin(db_session)
    brand = _client(db_session, admin, 'Delete Me Co')
    contact_id = _contact(db_session, brand).id
    brand_id = brand.id
    login_as(client, app, admin, 'password123')

    resp = _delete(app, client, brand_id)

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    db_session.expire_all()
    assert db_session.get(Client, brand_id) is None
    assert db_session.get(Contact, contact_id) is None


def test_a_client_on_a_project_is_refused(app, client, db_session):
    admin = _admin(db_session)
    brand = _client(db_session, admin, 'Busy Brand')
    contact = _contact(db_session, brand)
    project = Project(name='Busy Project', client_id=brand.id, contact_id=contact.id,
                      cs_lead_id=admin.id, created_by_id=admin.id)
    db_session.add(project)
    db_session.flush()
    login_as(client, app, admin, 'password123')

    resp = _delete(app, client, brand.id)

    assert resp.status_code == 400
    body = resp.get_json()
    assert body['success'] is False and '1 project' in body['error']
    db_session.expire_all()
    assert db_session.get(Client, brand.id) is not None


def test_a_client_with_deliverable_types_is_refused(app, client, db_session):
    admin = _admin(db_session)
    brand = _client(db_session, admin, 'Typed Brand')
    customer = Customer(name='Typed Customer', region='uae')
    db_session.add(customer)
    db_session.flush()
    db_session.add(DeliverableType(name='Gondola', client_id=brand.id, customer_id=customer.id))
    db_session.flush()
    login_as(client, app, admin, 'password123')

    resp = _delete(app, client, brand.id)

    assert resp.status_code == 400
    assert 'deliverable type' in resp.get_json()['error']
