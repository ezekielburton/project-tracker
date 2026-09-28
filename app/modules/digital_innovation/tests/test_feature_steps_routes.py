"""Route tests for the step actions (add, tick, delete) and closing a
feature: auth, 404s, validation, and step_engine ValueErrors as 400s."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject, DiFeatureStep, DI_STAGES
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.tests.test_features_routes import _user


def _project(db_session, tag, lifecycle='active', is_permanent=False):
    # is_permanent=True stands in for the OVP board, the only board every
    # role can view. Other test files import this helper.
    project = DiProject(name=f'Test DI Project {tag}', lifecycle=lifecycle, is_permanent=is_permanent)
    db_session.add(project)
    db_session.flush()
    return project


# ── add step ────────────────────────────────────────────────────────────

def test_add_step_requires_auth(app, client, db_session):
    project = _project(db_session, 'a')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': 'A step'})
    assert resp.status_code in (302, 401)


def test_add_step_happy_path(app, client, db_session):
    user = _user(db_session, 'b')
    project = _project(db_session, 'b')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': 'Draft the brief'})

    assert resp.status_code == 200
    assert 'Draft the brief' in resp.get_data(as_text=True)
    assert any(s.title == 'Draft the brief' for s in feature.steps)


def test_add_step_requires_a_title(app, client, db_session):
    user = _user(db_session, 'c')
    project = _project(db_session, 'c')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': '   '})
    assert resp.status_code == 400


def test_add_step_stores_details_when_provided(app, client, db_session):
    user = _user(db_session, 'c2')
    project = _project(db_session, 'c2')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': 'Data model', 'details': 'Design the full-text index.'})

    assert resp.status_code == 200
    step = next(s for s in feature.steps if s.title == 'Data model')
    assert step.details == 'Design the full-text index.'


def test_add_step_details_is_optional(app, client, db_session):
    user = _user(db_session, 'c3')
    project = _project(db_session, 'c3')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': 'Just a title'})

    assert resp.status_code == 200
    step = next(s for s in feature.steps if s.title == 'Just a title')
    assert step.details is None


def test_add_step_404s_for_an_unknown_feature(app, client, db_session):
    user = _user(db_session, 'd')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=999999)
    resp = client.post(url, json={'title': 'A step'})
    assert resp.status_code == 404


def test_add_step_rejects_a_closed_feature(app, client, db_session):
    user = _user(db_session, 'e')
    project = _project(db_session, 'e')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    engine.close_feature(feature)
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.add_feature_step', feature_id=feature.id)
    resp = client.post(url, json={'title': 'Too late'})
    assert resp.status_code == 400


# ── tick step ───────────────────────────────────────────────────────────

def test_tick_step_marks_it_done(app, client, db_session):
    user = _user(db_session, 'f')
    project = _project(db_session, 'f')
    feature = engine.create_feature(project, 'New thing')
    step = engine.add_step(feature, 'One')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.tick_feature_step', step_id=step.id)
    resp = client.post(url, json={'done': True})

    assert resp.status_code == 200
    assert DiFeatureStep.query.get(step.id).is_done is True


def test_tick_step_can_untick_it(app, client, db_session):
    user = _user(db_session, 'g')
    project = _project(db_session, 'g')
    feature = engine.create_feature(project, 'New thing')
    step = engine.add_step(feature, 'One')
    engine.tick_step(step, done=True)
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.tick_feature_step', step_id=step.id)
    resp = client.post(url, json={'done': False})

    assert resp.status_code == 200
    assert DiFeatureStep.query.get(step.id).is_done is False


def test_tick_step_404s_for_an_unknown_step(app, client, db_session):
    user = _user(db_session, 'h')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.tick_feature_step', step_id=999999)
    resp = client.post(url, json={'done': True})
    assert resp.status_code == 404


def test_tick_step_rejects_a_step_from_an_earlier_stage(app, client, db_session):
    user = _user(db_session, 'i')
    project = _project(db_session, 'i')
    feature = engine.create_feature(project, 'New thing')
    old_step = engine.add_step(feature, 'From researching')
    feature.status = DI_STAGES[1]
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.tick_feature_step', step_id=old_step.id)
    resp = client.post(url, json={'done': True})
    assert resp.status_code == 400


# ── delete step ─────────────────────────────────────────────────────────

def test_delete_step_removes_it(app, client, db_session):
    user = _user(db_session, 'j')
    project = _project(db_session, 'j')
    feature = engine.create_feature(project, 'New thing')
    step = engine.add_step(feature, 'One')
    engine.add_step(feature, 'Two')
    db_session.flush()
    step_id = step.id
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_feature_step', step_id=step_id)
    resp = client.delete(url)

    assert resp.status_code == 200
    assert DiFeatureStep.query.get(step_id) is None


def test_delete_step_does_not_change_stage(app, client, db_session):
    user = _user(db_session, 'k')
    project = _project(db_session, 'k')
    feature = engine.create_feature(project, 'New thing')
    done_step = engine.add_step(feature, 'Done already')
    last_step = engine.add_step(feature, 'The blocker')
    engine.tick_step(done_step, done=True)
    db_session.flush()
    starting_stage = feature.status
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_feature_step', step_id=last_step.id)
    resp = client.delete(url)

    assert resp.status_code == 200
    assert feature.status == starting_stage  # deleting a step never moves the stage


def test_delete_step_404s_for_an_unknown_step(app, client, db_session):
    user = _user(db_session, 'l')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_feature_step', step_id=999999)
    resp = client.delete(url)
    assert resp.status_code == 404



# ── close feature ───────────────────────────────────────────────────────

def test_close_feature_closes_it_once_implementation_is_done(app, client, db_session):
    user = _user(db_session, 'q')
    project = _project(db_session, 'q')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    step = engine.add_step(feature, 'Only step')
    engine.tick_step(step, done=True)
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_feature_route', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 200
    assert feature.status == 'closed'


def test_close_feature_rejects_before_implementation_steps_are_done(app, client, db_session):
    user = _user(db_session, 'r')
    project = _project(db_session, 'r')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    engine.add_step(feature, 'Not done yet')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_feature_route', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 400
    assert feature.status != 'closed'


def test_close_feature_rejects_before_implementation_stage(app, client, db_session):
    user = _user(db_session, 's')
    project = _project(db_session, 's')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.close_feature_route', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 400
    assert feature.status != 'closed'


def test_close_feature_requires_auth(app, client, db_session):
    project = _project(db_session, 't')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    db_session.flush()

    with app.test_request_context():
        url = url_for('digital_innovation.close_feature_route', feature_id=feature.id)
    resp = client.post(url)
    assert resp.status_code in (302, 401)


# ── reopen feature ──────────────────────────────────────────────────────

def _closed_feature(db_session, tag):
    project = _project(db_session, tag)
    feature = engine.create_feature(project, 'Done thing', starting_stage=DI_STAGES[-1])
    engine.close_feature(feature)
    db_session.flush()
    return feature


def test_reopen_feature_puts_it_back_in_the_last_stage(app, client, db_session):
    user = _user(db_session, 'ro-a')
    feature = _closed_feature(db_session, 'ro-a')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.reopen_feature_route', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 200
    assert feature.status == DI_STAGES[-1]
    assert feature.closed_at is None
    # The fragment is the open-feature view again: the stage picker is back.
    assert 'di-stage-picker-select' in resp.get_data(as_text=True)


def test_closed_feature_detail_shows_the_reopen_button_to_editors_only(app, client, db_session):
    feature = _closed_feature(db_session, 'ro-b')
    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)

    login_as(client, app, _user(db_session, 'ro-b-admin'), 'password123')
    assert 'di-reopen-feature-btn' in client.get(url).get_data(as_text=True)

    # A fresh client, so the admin's session does not carry over.
    viewer = app.test_client()
    login_as(viewer, app, _user(db_session, 'ro-b-mgmt', role='management'), 'password123')
    resp = viewer.get(url)
    assert resp.status_code == 200
    assert 'di-reopen-feature-btn' not in resp.get_data(as_text=True)


def test_reopen_feature_rejects_an_open_feature(app, client, db_session):
    user = _user(db_session, 'ro-c')
    project = _project(db_session, 'ro-c')
    feature = engine.create_feature(project, 'Open thing')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.reopen_feature_route', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 400
    assert feature.status == DI_STAGES[0]


def test_reopen_feature_403s_without_board_write_access(app, client, db_session):
    user = _user(db_session, 'ro-d', role='management')
    feature = _closed_feature(db_session, 'ro-d')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.reopen_feature_route', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 403
    assert feature.status == 'closed'


def test_reopen_feature_requires_auth(app, client, db_session):
    feature = _closed_feature(db_session, 'ro-e')
    with app.test_request_context():
        url = url_for('digital_innovation.reopen_feature_route', feature_id=feature.id)
    resp = client.post(url)
    assert resp.status_code in (302, 401)
