"""Closing a project from Client Servicing — the gate, the normal close,
and the cancelled project's two-step invoicing answer."""
import re
from datetime import date, datetime

from flask import url_for

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing


def _user(db_session, tag, role='cs'):
    user = User(name=f'Closer {tag}', email=f'cs-close-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, user, name='Closable Project', cancelled=False, value=None):
    # value lives on Project, not CS. Seed it so the close-out doesn't ask for one.
    project = Project(
        name=name, cs_lead_id=user.id, created_by_id=user.id, project_status='briefed',
    )
    if value is not None:
        project.value = value
    if cancelled:
        project.cancelled_at = datetime.utcnow()
    db_session.add(project)
    db_session.flush()
    return project


def _close_url(app, project):
    with app.test_request_context():
        return url_for('client_servicing.close_project', project_id=project.id)


def _table_url(app):
    with app.test_request_context():
        return url_for('client_servicing.table')


def test_project_owner_cannot_close(app, client, db_session):
    """A project owner can open the module but cannot close a project."""
    owner = _user(db_session, 'a', role='project_owner')
    project = _project(db_session, owner)
    login_as(client, app, owner, 'password123')

    resp = client.post(_close_url(app, project), json={})
    assert resp.status_code == 403


def test_finance_cannot_close(app, client, db_session):
    user = _user(db_session, 'b', role='finance')
    project = _project(db_session, user)
    login_as(client, app, user, 'password123')

    resp = client.post(_close_url(app, project), json={})
    assert resp.status_code == 403


def test_cs_lead_closes_a_live_project(app, client, db_session):
    user = _user(db_session, 'c')
    project = _project(db_session, user)
    login_as(client, app, user, 'password123')

    resp = client.post(_close_url(app, project), json={})
    assert resp.status_code == 200

    cs = ClientServicing.query.filter_by(project_id=project.id).one()
    assert cs.closed_at is not None
    assert cs.closed_by_id == user.id
    assert cs.invoice_needed is None
    assert cs.is_closed is True


def test_closing_twice_is_refused(app, client, db_session):
    user = _user(db_session, 'd')
    project = _project(db_session, user)
    login_as(client, app, user, 'password123')

    assert client.post(_close_url(app, project), json={}).status_code == 200
    assert client.post(_close_url(app, project), json={}).status_code == 409


def test_cancelled_project_needs_the_invoicing_answer(app, client, db_session):
    user = _user(db_session, 'e')
    project = _project(db_session, user, cancelled=True)
    login_as(client, app, user, 'password123')

    resp = client.post(_close_url(app, project), json={})
    assert resp.status_code == 400
    assert ClientServicing.query.filter_by(project_id=project.id).first() is None


def test_cancelled_project_with_nothing_to_invoice(app, client, db_session):
    user = _user(db_session, 'f')
    project = _project(db_session, user, cancelled=True)
    login_as(client, app, user, 'password123')

    resp = client.post(_close_url(app, project), json={'invoice_needed': False})
    assert resp.status_code == 200

    cs = ClientServicing.query.filter_by(project_id=project.id).one()
    assert cs.invoice_needed is False
    assert cs.close_invoice_state == 'not_needed'


def test_cancelled_project_already_invoiced_stores_the_date(app, client, db_session):
    user = _user(db_session, 'g')
    # Already has a value, so the close-out isn't asked for one.
    project = _project(db_session, user, cancelled=True, value=5000)
    login_as(client, app, user, 'password123')

    resp = client.post(
        _close_url(app, project),
        json={'invoice_needed': True, 'invoice_date': '2026-08-14'},
    )
    assert resp.status_code == 200

    cs = ClientServicing.query.filter_by(project_id=project.id).one()
    assert cs.invoice_date == date(2026, 8, 14)
    assert cs.close_invoice_state == 'invoiced'


def test_cancelled_project_not_invoiced_yet_is_pending(app, client, db_session):
    user = _user(db_session, 'h')
    # Already has a value, so the close-out isn't asked for one.
    project = _project(db_session, user, cancelled=True, value=5000)
    login_as(client, app, user, 'password123')

    resp = client.post(_close_url(app, project), json={'invoice_needed': True})
    assert resp.status_code == 200

    cs = ClientServicing.query.filter_by(project_id=project.id).one()
    assert cs.invoice_date is None
    assert cs.close_invoice_state == 'pending'


def test_a_bad_invoice_date_is_rejected(app, client, db_session):
    user = _user(db_session, 'i')
    project = _project(db_session, user, cancelled=True)
    login_as(client, app, user, 'password123')

    resp = client.post(
        _close_url(app, project),
        json={'invoice_needed': True, 'invoice_date': 'the 14th'},
    )
    assert resp.status_code == 400
    assert ClientServicing.query.filter_by(project_id=project.id).first() is None


def test_cancelled_project_waits_in_the_close_out_strip(app, client, db_session):
    user = _user(db_session, 'j')
    _project(db_session, user, name='Cancelled Kiosk Pilot', cancelled=True)
    login_as(client, app, user, 'password123')

    html = client.get(_table_url(app)).get_data(as_text=True)
    assert 'cs-closeout-btn' in html
    assert 'Cancelled Kiosk Pilot' in html


def test_close_out_strip_hidden_from_a_role_that_cannot_close(app, client, db_session):
    owner = _user(db_session, 'k', role='project_owner')
    _project(db_session, owner, name='Cancelled Window Vinyl', cancelled=True)
    login_as(client, app, owner, 'password123')

    html = client.get(_table_url(app)).get_data(as_text=True)
    assert 'cs-closeout-btn' not in html
    assert 'cs-close-btn' not in html


def test_close_out_skips_the_value_question_when_the_project_has_one(app, client, db_session):
    """The close-out prompt asks for a value only when Project.value is empty."""
    user = _user(db_session, 'm')
    _project(db_session, user, name='Valued Cancelled Job', cancelled=True, value=12000)
    _project(db_session, user, name='Unvalued Cancelled Job', cancelled=True)
    login_as(client, app, user, 'password123')

    html = client.get(_table_url(app)).get_data(as_text=True)

    def has_value(name):
        match = re.search(r'data-has-value="(\d)"\s+data-project-name="[^"]*\b' + name + '"', html)
        return match.group(1)

    assert has_value('Valued Cancelled Job') == '1'
    assert has_value('Unvalued Cancelled Job') == '0'
