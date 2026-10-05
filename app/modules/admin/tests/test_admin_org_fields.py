"""Editing the org fields in Admin → Accounts: what saves, what is refused, and
that only an admin (the real one, when emulating) can do it."""
import pytest
from flask import url_for

from app.modules.core.shared.models import JobRole, User
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role='designer', **fields):
    user = User(name=f'Org Admin {tag}', email=f'org-admin-{tag}@example.com', role=role, **fields)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _login_admin(app, client, db_session, tag='admin'):
    admin = _user(db_session, tag, role='admin')
    login_as(client, app, admin, 'password123')
    return admin


def _patch(client, user, **fields):
    return client.patch(f'/admin/api/users/{user.id}', json={'name': user.name, 'email': user.email, **fields})


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def test_logged_out_is_refused(app, client):
    assert client.get(_url(app, 'admin.org_options')).status_code in (302, 401, 403)


def test_admin_sets_the_org_fields(app, client, db_session):
    _login_admin(app, client, db_session)
    boss = _user(db_session, 'boss', role='management')
    person = _user(db_session, 'person', team='2D')

    resp = _patch(client, person, department='finance', job_title='Senior Accountant',
                  seniority='head', reports_to_id=boss.id, is_admin=False)
    assert resp.status_code == 200
    data = resp.get_json()['user']
    assert (data['department'], data['job_title'], data['seniority'], data['reports_to_id']) == \
        ('finance', 'Senior Accountant', 'head', boss.id)
    assert data['team'] is None


def test_fields_left_out_keep_their_value(app, client, db_session):
    _login_admin(app, client, db_session)
    boss = _user(db_session, 'keep-boss', role='management')
    person = _user(db_session, 'keep', reports_to_id=boss.id, team='3D')
    assert _patch(client, person, seniority='manager').status_code == 200
    db_session.expire_all()
    person = db_session.get(User, person.id)
    assert (person.department, person.team, person.reports_to_id) == ('design', '3D', boss.id)


def test_a_typed_title_joins_the_department_list_once(app, client, db_session):
    _login_admin(app, client, db_session)
    a = _user(db_session, 'title-a')
    b = _user(db_session, 'title-b')
    _patch(client, a, department='hr', job_title='People Partner')
    _patch(client, b, department='hr', job_title='people  partner')
    db_session.expire_all()
    assert JobRole.query.filter_by(department='hr').filter(JobRole.title.ilike('people partner')).count() == 1
    assert db_session.get(User, a.id).job_role_id == db_session.get(User, b.id).job_role_id


@pytest.mark.parametrize('field, value', [
    ('department', 'astronauts'), ('seniority', 'emperor'), ('team', 'Bogus'), ('reports_to_id', 'abc'),
])
def test_unknown_values_are_refused(app, client, db_session, field, value):
    _login_admin(app, client, db_session)
    person = _user(db_session, f'bad-{field}')
    assert _patch(client, person, **{field: value}).status_code == 400


def test_reports_to_cannot_be_yourself_or_make_a_loop(app, client, db_session):
    _login_admin(app, client, db_session)
    lead = _user(db_session, 'loop-lead', role='team_lead')
    designer = _user(db_session, 'loop-designer', reports_to_id=lead.id)
    assert _patch(client, lead, reports_to_id=lead.id).status_code == 400
    assert _patch(client, lead, reports_to_id=designer.id).status_code == 400


def test_you_cannot_remove_your_own_admin(app, client, db_session):
    admin = _login_admin(app, client, db_session)
    assert _patch(client, admin, is_admin=False).status_code == 400
    assert _patch(client, admin, department='digital_innovation', seniority='head').status_code == 200


def test_creating_a_user_sets_the_org_fields(app, client, db_session):
    _login_admin(app, client, db_session)
    resp = client.post('/admin/api/users', json={
        'name': 'Org Admin new', 'email': 'org-admin-new@example.com', 'password': 'password123',
        'department': 'production', 'job_title': 'Workshop Supervisor', 'seniority': 'manager',
    })
    assert resp.status_code == 200
    user = User.query.filter_by(email='org-admin-new@example.com').one()
    assert (user.department, user.seniority, user.job_role.title) == ('production', 'manager', 'Workshop Supervisor')


def test_job_titles_rename_and_hide(app, client, db_session):
    _login_admin(app, client, db_session)
    row = JobRole(department='finance', title='Org Admin Clerk')
    db_session.add(row)
    db_session.flush()

    resp = client.patch(f'/admin/api/job-titles/{row.id}', json={'title': 'Org Admin Accounts Clerk', 'is_active': False})
    assert resp.status_code == 200
    titles = client.get(_url(app, 'admin.org_options')).get_json()['titles']
    assert 'Org Admin Accounts Clerk' not in titles.get('finance', [])


def test_renaming_onto_an_existing_title_is_refused(app, client, db_session):
    _login_admin(app, client, db_session)
    first = JobRole(department='finance', title='Org Admin One')
    second = JobRole(department='finance', title='Org Admin Two')
    db_session.add_all([first, second])
    db_session.flush()
    assert client.patch(f'/admin/api/job-titles/{second.id}', json={'title': 'org admin one'}).status_code == 400


@pytest.mark.parametrize('method, endpoint', [
    ('get', 'admin.org_options'), ('get', 'admin.list_job_titles'),
])
def test_non_admins_are_refused(app, client, db_session, method, endpoint):
    login_as(client, app, _user(db_session, f'gate-{endpoint}', role='management'), 'password123')
    assert getattr(client, method)(_url(app, endpoint)).status_code == 403


def test_a_non_admin_cannot_edit_a_job_title(app, client, db_session):
    row = JobRole(department='finance', title='Org Admin Gate')
    db_session.add(row)
    db_session.flush()
    login_as(client, app, _user(db_session, 'gate-patch', role='hr'), 'password123')
    assert client.patch(f'/admin/api/job-titles/{row.id}', json={'title': 'x'}).status_code == 403


def test_an_emulating_admin_keeps_account_editing(app, client, db_session):
    _login_admin(app, client, db_session, 'emu-admin')
    target = _user(db_session, 'emu-target')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = target.id
    assert _patch(client, target, seniority='manager').status_code == 200


def test_the_register_page_is_gone(app, client, db_session):
    _login_admin(app, client, db_session, 'register-admin')
    assert client.get('/register').status_code == 404
