"""Coverage for CS emulation-awareness.

Every route in this module used to read current_user directly for its
access check, saved layout, and edit-attribution — so an admin emulating
a lower-role user (session['emulating_user_id'], the same mechanism
Projects/Dashboard already use) could still open and use the page,
since current_user is always the real, logged-in admin regardless of
who's being emulated. lib/access.py's _effective_user() fixes that; these
tests lock the fix in and pin down the one deliberate exception (the
Scope-management CRUD, which is genuinely admin-only and stays on
current_user on purpose)."""
import json

from flask import url_for

from app.modules.core.shared.models import User, Project, UserTableLayout, Notification
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.routes.table import TABLE_KEY


def _user(db_session, tag, role='cs', name=None):
    user = User(name=name or f'Emulation Test {tag}', email=f'cs-emu-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _emulate(client, target_user):
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = target_user.id


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def test_index_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    admin = _user(db_session, 'a', role='admin')
    designer = _user(db_session, 'a2', role='designer')
    login_as(client, app, admin, 'password123')
    _emulate(client, designer)

    resp = client.get(_url(app, 'client_servicing.index'))
    assert resp.status_code == 403


def test_table_rows_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    """The SSE live-refresh fragment endpoint has its own _require_access()
    call, independent of index() — worth its own test since a fix to one
    doesn't guarantee the other got fixed too."""
    admin = _user(db_session, 'b', role='admin')
    designer = _user(db_session, 'b2', role='designer')
    login_as(client, app, admin, 'password123')
    _emulate(client, designer)

    resp = client.get(_url(app, 'client_servicing.table_rows'))
    assert resp.status_code == 403


def test_index_200s_for_an_admin_emulating_an_allowed_role(app, client, db_session):
    """Sanity check for the other direction: emulating a role that DOES
    have CS access should still work, same as that role logging in for
    real would."""
    admin = _user(db_session, 'c', role='admin')
    cs_user = _user(db_session, 'c2', role='cs')
    login_as(client, app, admin, 'password123')
    _emulate(client, cs_user)

    resp = client.get(_url(app, 'client_servicing.index'))
    assert resp.status_code == 200


def test_edit_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    admin = _user(db_session, 'd', role='admin')
    designer = _user(db_session, 'd2', role='designer')
    # job_number is a plain Project field update_field() writes directly
    # (unlike lpo, which lives on the ClientServicing extension row and
    # isn't a Project constructor kwarg at all).
    project = Project(name='Emulation Edit Test', cs_lead_id=admin.id, created_by_id=admin.id, job_number='OLD')
    db_session.add(project)
    db_session.flush()
    login_as(client, app, admin, 'password123')
    _emulate(client, designer)

    resp = client.patch(
        _url(app, 'client_servicing.update_field', project_id=project.id),
        data=json.dumps({'field': 'job_number', 'value': 'NEW'}), content_type='application/json',
    )
    assert resp.status_code == 403
    db_session.refresh(project)
    assert project.job_number == 'OLD'  # nothing actually got written


def test_quick_add_scope_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    admin = _user(db_session, 'e', role='admin')
    designer = _user(db_session, 'e2', role='designer')
    login_as(client, app, admin, 'password123')
    _emulate(client, designer)

    resp = client.post(
        _url(app, 'client_servicing.quick_add_scope'),
        data=json.dumps({'name': 'Should Not Be Added'}), content_type='application/json',
    )
    assert resp.status_code == 403


def test_admin_only_scope_crud_still_works_while_emulating_a_designer(app, client, db_session):
    """Deliberate exception, not an oversight: list/create/rename/
    deactivate are gated by @role_required('admin'), which — like every
    other genuinely admin-only write route in this app — stays on
    current_user on purpose, so an admin previewing the app as someone
    else doesn't lose access to real admin tools mid-preview."""
    admin = _user(db_session, 'f', role='admin')
    designer = _user(db_session, 'f2', role='designer')
    login_as(client, app, admin, 'password123')
    _emulate(client, designer)

    resp = client.post(
        _url(app, 'client_servicing.create_scope'),
        data=json.dumps({'name': 'Still Admin Even While Emulating'}), content_type='application/json',
    )
    assert resp.status_code == 200


def test_saved_layout_is_scoped_to_the_emulated_user_not_the_real_admin(app, client, db_session):
    admin = _user(db_session, 'g', role='admin')
    cs_user = _user(db_session, 'g2', role='cs')
    login_as(client, app, admin, 'password123')
    _emulate(client, cs_user)

    resp = client.post(
        _url(app, 'client_servicing.save_layout'),
        data=json.dumps({'table_key': TABLE_KEY, 'layout': [{'key': 'client', 'width': 150}]}),
        content_type='application/json',
    )
    assert resp.status_code == 200

    # Saved against the emulated user, not the real admin underneath.
    assert UserTableLayout.query.filter_by(user_id=cs_user.id, table_key=TABLE_KEY).first() is not None
    assert UserTableLayout.query.filter_by(user_id=admin.id, table_key=TABLE_KEY).first() is None


def test_reassign_cs_lead_while_emulating_attributes_the_notification_to_the_emulated_user(app, client, db_session):
    # Deliberately non-overlapping names (not _user()'s default
    # "Emulation Test {tag}" shape) — "Test h" is a literal substring of
    # "Test h2", which made the admin.name-not-in-message assertion
    # below pass or fail on accident rather than on the actual behaviour
    # being tested.
    admin = _user(db_session, 'h', role='admin', name='Real Admin Underneath')
    management_user = _user(db_session, 'h2', role='management', name='Emulated Manager')  # has CS access, can trigger a reassign
    new_lead = _user(db_session, 'h3', role='cs')
    project = Project(name='Emulation Attribution Test', cs_lead_id=admin.id, created_by_id=admin.id)
    db_session.add(project)
    db_session.flush()
    login_as(client, app, admin, 'password123')
    _emulate(client, management_user)

    resp = client.patch(
        _url(app, 'client_servicing.update_field', project_id=project.id),
        data=json.dumps({'field': 'cs_lead_id', 'value': new_lead.id}), content_type='application/json',
    )
    assert resp.status_code == 200

    notification = Notification.query.filter_by(recipient_id=new_lead.id, notification_type='cs_lead_reassigned').first()
    assert notification is not None
    assert notification.triggered_by_id == management_user.id  # the emulated identity, not the real admin
    assert management_user.name in notification.message
    assert admin.name not in notification.message
