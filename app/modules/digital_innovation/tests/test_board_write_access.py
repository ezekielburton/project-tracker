"""Coverage for the board write-access gate (can_edit_di_board,
lib/access.py) — "read only to everyone except me and my future team". The board itself (viewing a project, opening a
feature) stays open to every logged-in user for the permanent OVP
board — a *separate* gate (can_view_di_project) hides
every other project from everyone except admin/management/future
digital_innovation, dedicated coverage in test_project_visibility.py.
This file stays about the six actions that change data: create a
feature, add/tick/delete a step, advance a stage, close a feature — so
every project built here for a write-gate test is the permanent OVP
stand-in (_feature_with_step, is_permanent=True) purely so a designer
can reach the write gate at all; it isn't what's being tested. Project
creation's own gate has its dedicated coverage in test_project_routes.py.

Each mutating route already has full happy-path/validation/404 coverage
elsewhere (test_features_routes.py, test_feature_steps_routes.py) using
_user()'s admin default — this file only adds the 403 side, plus the
template-rendering assertions that a read-only viewer's HTML genuinely
has no interactive controls in it (not just disabled ones)."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiFeatureStep, DI_STAGES
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project


def _feature_with_step(db_session, tag):
    # is_permanent=True: these tests are about the write
    # gate (can_edit_di_board), not the separate visibility gate
    # (can_view_di_project) - standing in for OVP keeps a designer able
    # to reach feature_detail/project_board at all, same as before that
    # second gate existed, so these assertions still isolate write-access.
    project = _project(db_session, tag, is_permanent=True)
    feature = engine.create_feature(project, 'New thing')
    step = engine.add_step(feature, 'Only step')
    db_session.flush()
    return project, feature, step


# ── create feature ──────────────────────────────────────────────────────

def test_create_feature_403s_for_a_designer(app, client, db_session):
    project = _project(db_session, 'wa')
    user = _user(db_session, 'wa', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': 'Should not exist'})
    assert resp.status_code == 403


def test_create_feature_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    project = _project(db_session, 'wb')
    admin = _user(db_session, 'wb', role='admin')
    designer = _user(db_session, 'wb2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': 'Should not exist'})
    assert resp.status_code == 403


# ── add step ────────────────────────────────────────────────────────────

def test_add_step_403s_for_a_designer(app, client, db_session):
    _, feature, _step = _feature_with_step(db_session, 'wc')
    user = _user(db_session, 'wc', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': 'Should not be added'})
    assert resp.status_code == 403


def test_add_step_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    _, feature, _step = _feature_with_step(db_session, 'wd')
    admin = _user(db_session, 'wd', role='admin')
    designer = _user(db_session, 'wd2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': 'Should not be added'})
    assert resp.status_code == 403


# ── tick step ───────────────────────────────────────────────────────────

def test_tick_step_403s_for_a_designer(app, client, db_session):
    _, _feature, step = _feature_with_step(db_session, 'we')
    user = _user(db_session, 'we', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.tick_feature_step', step_id=step.id)
    resp = client.post(url, json={'done': True})

    assert resp.status_code == 403
    assert DiFeatureStep.query.get(step.id).is_done is False


def test_tick_step_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    _, _feature, step = _feature_with_step(db_session, 'wf')
    admin = _user(db_session, 'wf', role='admin')
    designer = _user(db_session, 'wf2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.tick_feature_step', step_id=step.id)
    resp = client.post(url, json={'done': True})
    assert resp.status_code == 403


# ── delete step ─────────────────────────────────────────────────────────

def test_delete_step_403s_for_a_designer(app, client, db_session):
    _, _feature, step = _feature_with_step(db_session, 'wg')
    step_id = step.id
    user = _user(db_session, 'wg', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_feature_step', step_id=step_id)
    resp = client.delete(url)

    assert resp.status_code == 403
    assert DiFeatureStep.query.get(step_id) is not None


def test_delete_step_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    _, _feature, step = _feature_with_step(db_session, 'wh')
    step_id = step.id
    admin = _user(db_session, 'wh', role='admin')
    designer = _user(db_session, 'wh2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.delete_feature_step', step_id=step_id)
    resp = client.delete(url)

    assert resp.status_code == 403
    assert DiFeatureStep.query.get(step_id) is not None


# ── move feature stage ──────────────────────────────────────────────────

def test_move_feature_stage_403s_for_a_designer(app, client, db_session):
    _, feature, step = _feature_with_step(db_session, 'wi')
    engine.tick_step(step, done=True)
    starting_stage = feature.status
    user = _user(db_session, 'wi', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.move_feature_stage', feature_id=feature.id)
    resp = client.post(url, json={'stage': 'planning'})

    assert resp.status_code == 403
    assert feature.status == starting_stage


def test_move_feature_stage_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    _, feature, step = _feature_with_step(db_session, 'wj')
    engine.tick_step(step, done=True)
    admin = _user(db_session, 'wj', role='admin')
    designer = _user(db_session, 'wj2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.move_feature_stage', feature_id=feature.id)
    resp = client.post(url, json={'stage': 'planning'})
    assert resp.status_code == 403


# ── close feature ───────────────────────────────────────────────────────

def test_close_feature_403s_for_a_designer(app, client, db_session):
    project = _project(db_session, 'wk')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    step = engine.add_step(feature, 'Only step')
    engine.tick_step(step, done=True)
    db_session.flush()
    user = _user(db_session, 'wk', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_feature_route', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 403
    assert feature.status != 'closed'


def test_close_feature_403s_for_an_admin_emulating_a_designer(app, client, db_session):
    project = _project(db_session, 'wl')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    step = engine.add_step(feature, 'Only step')
    engine.tick_step(step, done=True)
    db_session.flush()
    admin = _user(db_session, 'wl', role='admin')
    designer = _user(db_session, 'wl2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.close_feature_route', feature_id=feature.id)
    resp = client.post(url)
    assert resp.status_code == 403


# ── feature detail rendering: controls are absent, not just disabled ────

def test_feature_detail_hides_every_control_from_a_designer(app, client, db_session):
    _, feature, step = _feature_with_step(db_session, 'wm')
    user = _user(db_session, 'wm', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'data-step-id' not in body
    assert 'di-step-delete' not in body
    assert 'di-step-add-btn' not in body
    assert 'id="di-step-add-title"' not in body
    assert 'di-advance-feature-btn' not in body
    assert 'di-close-feature-btn' not in body
    assert 'di-step--readonly' in body


def test_feature_detail_shows_every_control_to_an_admin(app, client, db_session):
    _, feature, step = _feature_with_step(db_session, 'wn')
    user = _user(db_session, 'wn', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert f'data-step-id="{step.id}"' in body
    assert 'di-step-delete' in body
    assert 'id="di-step-add-title"' in body
    assert 'di-step--readonly' not in body


def test_feature_detail_controls_are_emulation_aware(app, client, db_session):
    # Same swap the cost footer already relies on: an admin emulating a
    # designer should see exactly what that designer would see.
    _, feature, _step = _feature_with_step(db_session, 'wo')
    admin = _user(db_session, 'wo', role='admin')
    designer = _user(db_session, 'wo2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'data-step-id' not in body
    assert 'id="di-step-add-title"' not in body


# ── board page rendering: "+ New project" / "+ Add feature" ─────────────

def test_board_hides_new_project_and_add_feature_from_a_designer(app, client, db_session):
    # is_permanent=True: this test is about write controls, not the
    # visibility gate - see _feature_with_step's comment above.
    project = _project(db_session, 'wp', is_permanent=True)
    user = _user(db_session, 'wp', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-new-project-trigger' not in body
    assert 'di-add-feature-trigger' not in body


def test_board_shows_new_project_and_add_feature_to_an_admin(app, client, db_session):
    project = _project(db_session, 'wq')
    user = _user(db_session, 'wq', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-new-project-trigger' in body
    assert 'di-add-feature-trigger' in body


def test_board_is_still_viewable_by_a_designer_on_the_permanent_ovp_board(app, client, db_session):
    # Viewing the permanent OVP board stays open to everyone — only
    # mutation is gated there. Viewing is an OVP-board guarantee; see the 403
    # test below for the rule on every other board.
    project = _project(db_session, 'wr', is_permanent=True)
    engine.create_feature(project, 'Visible to everyone')
    db_session.flush()
    user = _user(db_session, 'wr', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Visible to everyone' in body


def test_board_403s_for_a_designer_on_a_non_permanent_project(app, client, db_session):
    # The visibility gate itself - a designer can't reach any board except the
    # permanent OVP one. Fuller
    # coverage of can_view_di_project lives in test_project_visibility.py;
    # this is here specifically as the counterpart to the OVP test above.
    project = _project(db_session, 'wr2')
    user = _user(db_session, 'wr2', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 403
