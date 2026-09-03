"""Coverage for the writeback fields: CS Lead, Project Owner,
Job No, Client SPOC, Installation Date, Project Value, Due Date — all
routed through app/modules/projects/services/mutations.py.

Also covers the notify-on-change behaviour for Due Date, Job No
and Client SPOC (designers + secondary CS + Project Owner, excluding the
actor and de-duplicated)."""
import json

from flask import url_for

from app.modules.core.shared.models import User, Project, Client, Contact, Notification, ProjectDesigner, ProjectSecondaryCS
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role='cs'):
    user = User(name=f'User {tag}', email=f'cs-wb-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, tag, cs_lead, **kwargs):
    project = Project(name=f'Writeback Test {tag}', cs_lead_id=cs_lead.id, created_by_id=cs_lead.id, **kwargs)
    db_session.add(project)
    db_session.flush()
    return project


def _patch(client, app, project_id, field, value):
    with app.test_request_context():
        url = url_for('client_servicing.update_field', project_id=project_id)
    return client.patch(url, data=json.dumps({'field': field, 'value': value}), content_type='application/json')


def test_any_cs_user_can_reassign_cs_lead_not_just_this_project(app, client, db_session):
    original_lead = _user(db_session, 'orig')
    other_cs_user = _user(db_session, 'actor')  # not assigned to the project at all
    new_lead = _user(db_session, 'new')
    project = _project(db_session, 'a', original_lead)
    login_as(client, app, other_cs_user, 'password123')

    resp = _patch(client, app, project.id, 'cs_lead_id', new_lead.id)
    assert resp.status_code == 200
    assert resp.get_json()['value'] == new_lead.name

    db_session.refresh(project)
    assert project.cs_lead_id == new_lead.id
    assert Notification.query.filter_by(recipient_id=new_lead.id, notification_type='cs_lead_reassigned').first()


def test_reassign_cs_lead_requires_cs_role_target(app, client, db_session):
    lead = _user(db_session, 'lead2')
    not_cs = _user(db_session, 'notcs', role='designer')
    project = _project(db_session, 'b', lead)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'cs_lead_id', not_cs.id)
    assert resp.status_code == 400


def test_set_project_owner_notifies_new_owner(app, client, db_session):
    lead = _user(db_session, 'lead3')
    owner = _user(db_session, 'owner', role='project_owner')
    project = _project(db_session, 'c', lead)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'project_owner_id', owner.id)
    assert resp.status_code == 200

    db_session.refresh(project)
    assert project.project_owner_id == owner.id
    assert Notification.query.filter_by(recipient_id=owner.id, notification_type='project_owner_assigned').first()


def test_due_date_saves(app, client, db_session):
    lead = _user(db_session, 'lead4')
    project = _project(db_session, 'd', lead)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'first_output_deadline', '2026-12-01')
    assert resp.status_code == 200

    db_session.refresh(project)
    assert project.first_output_deadline.isoformat() == '2026-12-01'


def test_job_number_must_be_unique(app, client, db_session):
    lead = _user(db_session, 'lead5')
    taken = _project(db_session, 'e', lead, job_number='JOB-TAKEN')
    project = _project(db_session, 'f', lead)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'job_number', 'JOB-TAKEN')
    assert resp.status_code == 400


def test_client_spoc_must_belong_to_project_client(app, client, db_session):
    lead = _user(db_session, 'lead6')
    client_a = Client(name='Client A', created_by_id=lead.id)
    client_b = Client(name='Client B', created_by_id=lead.id)
    db_session.add_all([client_a, client_b])
    db_session.flush()
    contact_on_b = Contact(name='Someone Else', client_id=client_b.id)
    db_session.add(contact_on_b)
    db_session.flush()
    project = _project(db_session, 'g', lead, client_id=client_a.id)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'contact_id', contact_on_b.id)
    assert resp.status_code == 400


def test_project_value_rejects_negative(app, client, db_session):
    lead = _user(db_session, 'lead7')
    project = _project(db_session, 'h', lead)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'value', -100)
    assert resp.status_code == 400


def test_due_date_change_notifies_designer_secondary_cs_and_owner_not_actor(app, client, db_session):
    lead = _user(db_session, 'lead8')
    designer = _user(db_session, 'designer8', role='designer')
    secondary = _user(db_session, 'secondary8')
    owner = _user(db_session, 'owner8', role='project_owner')
    project = _project(db_session, 'i', lead, project_owner_id=owner.id)
    db_session.add(ProjectDesigner(project_id=project.id, user_id=designer.id, team='2D'))
    db_session.add(ProjectSecondaryCS(project_id=project.id, user_id=secondary.id))
    db_session.flush()
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'first_output_deadline', '2026-12-15')
    assert resp.status_code == 200

    for recipient_id in (designer.id, secondary.id, owner.id):
        assert Notification.query.filter_by(recipient_id=recipient_id, notification_type='due_date_changed').first()
    # the actor (lead) shouldn't notify themselves
    assert Notification.query.filter_by(recipient_id=lead.id, notification_type='due_date_changed').first() is None


def test_due_date_unchanged_does_not_notify(app, client, db_session):
    lead = _user(db_session, 'lead9')
    secondary = _user(db_session, 'secondary9')
    from datetime import date
    project = _project(db_session, 'j', lead, first_output_deadline=date(2026, 12, 15))
    db_session.add(ProjectSecondaryCS(project_id=project.id, user_id=secondary.id))
    db_session.flush()
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'first_output_deadline', '2026-12-15')
    assert resp.status_code == 200
    assert Notification.query.filter_by(recipient_id=secondary.id, notification_type='due_date_changed').first() is None


def test_job_number_change_notifies_secondary_cs_and_owner(app, client, db_session):
    lead = _user(db_session, 'lead10')
    secondary = _user(db_session, 'secondary10')
    owner = _user(db_session, 'owner10', role='project_owner')
    project = _project(db_session, 'k', lead, project_owner_id=owner.id)
    db_session.add(ProjectSecondaryCS(project_id=project.id, user_id=secondary.id))
    db_session.flush()
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'job_number', 'JOB-500')
    assert resp.status_code == 200

    for recipient_id in (secondary.id, owner.id):
        assert Notification.query.filter_by(recipient_id=recipient_id, notification_type='job_number_changed').first()
    # due-date-only recipient list (designers) shouldn't apply here — nothing to assert
    # beyond the two above, since no designer was assigned.


def test_client_spoc_change_notifies_secondary_cs_and_owner(app, client, db_session):
    lead = _user(db_session, 'lead11')
    secondary = _user(db_session, 'secondary11')
    owner = _user(db_session, 'owner11', role='project_owner')
    biz_client = Client(name='Client C', created_by_id=lead.id)
    db_session.add(biz_client)
    db_session.flush()
    contact = Contact(name='Jane SPOC', client_id=biz_client.id)
    db_session.add(contact)
    project = _project(db_session, 'l', lead, client_id=biz_client.id, project_owner_id=owner.id)
    db_session.add(ProjectSecondaryCS(project_id=project.id, user_id=secondary.id))
    db_session.flush()
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'contact_id', contact.id)
    assert resp.status_code == 200

    for recipient_id in (secondary.id, owner.id):
        assert Notification.query.filter_by(recipient_id=recipient_id, notification_type='client_spoc_changed').first()


def test_secondary_cs_who_is_also_owner_only_notified_once(app, client, db_session):
    lead = _user(db_session, 'lead12')
    dual = _user(db_session, 'dual12', role='project_owner')
    project = _project(db_session, 'm', lead, project_owner_id=dual.id)
    db_session.add(ProjectSecondaryCS(project_id=project.id, user_id=dual.id))
    db_session.flush()
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'job_number', 'JOB-501')
    assert resp.status_code == 200

    assert Notification.query.filter_by(recipient_id=dual.id, notification_type='job_number_changed').count() == 1


def test_cs_lead_reassign_response_includes_avatar_chip_data(app, client, db_session):
    """The save response carries the new lead's person info so
    the cell can show the real avatar chip immediately, not plain text
    until the next refresh."""
    lead = _user(db_session, 'lead13')
    new_lead = _user(db_session, 'newlead13')
    project = _project(db_session, 'n', lead)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'cs_lead_id', new_lead.id)
    assert resp.status_code == 200
    person = resp.get_json()['person']
    assert person['id'] == new_lead.id
    assert person['name'] == new_lead.name


def test_project_owner_response_includes_avatar_chip_data(app, client, db_session):
    lead = _user(db_session, 'lead14')
    owner = _user(db_session, 'owner14', role='project_owner')
    project = _project(db_session, 'o', lead)
    login_as(client, app, lead, 'password123')

    resp = _patch(client, app, project.id, 'project_owner_id', owner.id)
    assert resp.status_code == 200
    person = resp.get_json()['person']
    assert person['id'] == owner.id
    assert person['name'] == owner.name
