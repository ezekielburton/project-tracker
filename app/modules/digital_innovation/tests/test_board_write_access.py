"""Tests for the board write gate (can_edit_di_board): the 403 side of the
six data-changing feature actions, and that a read-only viewer's HTML has
no interactive controls at all (not just disabled ones).

Projects here use is_permanent=True so a designer passes the separate
visibility gate (tested in test_project_visibility.py)."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiFeatureStep, DI_STAGES
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project


def _feature_with_step(db_session, tag):
    # is_permanent=True so a designer passes the visibility gate and these
    # tests isolate the write gate.
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
    # An admin emulating a designer sees what the designer sees.
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
    # is_permanent=True: see _feature_with_step.
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
    # Everyone can view the permanent board; only writes are gated.
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
    # Counterpart to the test above: a designer can't view any other board.
    project = _project(db_session, 'wr2')
    user = _user(db_session, 'wr2', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 403
