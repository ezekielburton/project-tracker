"""CS operational status — the cs_status overlay, effective status,
design indicators, and the inline edit that sets/clears it."""
import json

from flask import url_for

from app.modules.core.shared.models import User, Project, Deliverable
from app.modules.core.shared.testing import login_as
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.lib.status import (
    effective_cs_status, cs_design_indicator,
)


def _user(db_session, tag, role='cs'):
    user = User(name=f'CS Status {tag}', email=f'cs-status-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, tag, user, **kwargs):
    project = Project(name=f'CS Status Project {tag}', cs_lead_id=user.id, created_by_id=user.id, **kwargs)
    db_session.add(project)
    db_session.flush()
    return project


def _deliverable(db_session, project, user, **kwargs):
    d = Deliverable(project_id=project.id, name='D', created_by_id=user.id, **kwargs)
    db_session.add(d)
    db_session.flush()
    return d


def _patch(client, app, project_id, value):
    with app.test_request_context():
        url = url_for('client_servicing.update_field', project_id=project_id)
    return client.patch(url, data=json.dumps({'field': 'cs_status', 'value': value}),
                        content_type='application/json')


# ── Model ──────────────────────────────────────────────────────────────
def test_cs_status_persists_and_clears(db_session):
    user = _user(db_session, 'model')
    project = _project(db_session, 'model', user)
    cs = ClientServicing(project_id=project.id, cs_status='Invoiced')
    db_session.add(cs)
    db_session.flush()
    assert project.client_servicing.cs_status == 'Invoiced'
    cs.cs_status = None
    db_session.flush()
    assert project.client_servicing.cs_status is None


# ── effective_cs_status ──────────────────────────────────────────────────
def test_manual_status_wins(db_session):
    user = _user(db_session, 'manual')
    project = _project(db_session, 'manual', user)
    db_session.add(ClientServicing(project_id=project.id, cs_status='Pending LPO'))
    db_session.flush()
    label, modifier, is_auto = effective_cs_status(project)
    assert (label, modifier, is_auto) == ('Pending LPO', 'oak', False)


def test_auto_in_design_when_no_manual(db_session):
    user = _user(db_session, 'auto')
    project = _project(db_session, 'auto', user)
    label, modifier, is_auto = effective_cs_status(project)
    assert (label, modifier, is_auto) == ('In Design', 'coral', True)


def test_briefed_relabelled_to_briefing(db_session):
    user = _user(db_session, 'brief')
    project = _project(db_session, 'brief', user, project_status='briefed')
    assert effective_cs_status(project) == ('Briefing', 'sky', True)


def test_handed_to_production_shows_in_production_alias(db_session):
    user = _user(db_session, 'handed')
    project = _project(db_session, 'handed', user)
    _deliverable(db_session, project, user, status='approved')  # needs nothing -> handed to production
    label, modifier, is_auto = effective_cs_status(project)
    assert (label, modifier, is_auto) == ('In Production', 'clover', True)
    # The display alias must not have touched the underlying project.
    assert project.project_status != 'handed_to_production'


# ── cs_design_indicator ──────────────────────────────────────────────────
def test_standard_indicator_shows_open_2d_stream(db_session):
    user = _user(db_session, 'ind2d')
    project = _project(db_session, 'ind2d', user, brief_type='standard')
    _deliverable(db_session, project, user, status='in_progress')  # keeps project In Design
    _deliverable(db_session, project, user, status='approved', needs_2d=True, status_2d='in_progress')
    assert effective_cs_status(project)[0] == 'In Design'
    assert cs_design_indicator(project) == ['2D']


def test_ccm_indicator_concept_and_kv_before_approval(db_session):
    user = _user(db_session, 'indccm')
    project = _project(db_session, 'indccm', user, brief_type='ccm')
    assert cs_design_indicator(project) == ['Concept & KV']


# ── Inline edit endpoint ──────────────────────────────────────────────────
def test_edit_sets_status_and_leaves_project_status_untouched(app, client, db_session):
    user = _user(db_session, 'edit')
    project = _project(db_session, 'edit', user)
    before = project.project_status
    login_as(client, app, user, 'password123')

    resp = _patch(client, app, project.id, 'Installed')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['value'] == 'Installed'
    assert body['status']['label'] == 'Installed'
    assert body['status']['is_auto'] is False

    cs = ClientServicing.query.filter_by(project_id=project.id).first()
    assert cs.cs_status == 'Installed'
    db_session.refresh(project)
    assert project.project_status == before


def test_edit_clear_reverts_to_auto(app, client, db_session):
    user = _user(db_session, 'clear')
    project = _project(db_session, 'clear', user)
    login_as(client, app, user, 'password123')

    _patch(client, app, project.id, 'Installed')
    resp = _patch(client, app, project.id, '')
    assert resp.status_code == 200
    assert resp.get_json()['status']['is_auto'] is True
    cs = ClientServicing.query.filter_by(project_id=project.id).first()
    assert cs.cs_status is None


def test_edit_rejects_unknown_status(app, client, db_session):
    user = _user(db_session, 'bad')
    project = _project(db_session, 'bad', user)
    login_as(client, app, user, 'password123')
    resp = _patch(client, app, project.id, 'Not A Real Status')
    assert resp.status_code == 400


def test_edit_permission_enforced(app, client, db_session):
    user = _user(db_session, 'perm', role='designer')
    project = _project(db_session, 'perm', user)
    login_as(client, app, user, 'password123')
    resp = _patch(client, app, project.id, 'Installed')
    assert resp.status_code == 403
