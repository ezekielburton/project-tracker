"""Route-level coverage for the feature detail modal's interactive
actions (chunk 4): add/tick/delete a step, advance a stage, close a
feature. step_engine.py (brain A) already has full unit coverage for the
rules themselves — these tests are about the HTTP layer: auth, 404s,
validation, and that a step_engine ValueError turns into a 400."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject, DiFeatureStep, DI_STAGES
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.tests.test_features_routes import _user


def _project(db_session, tag, lifecycle='active'):
    project = DiProject(name=f'Test DI Project {tag}', lifecycle=lifecycle)
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


def test_delete_step_auto_advances_when_it_was_the_last_undone_step(app, client, db_session):
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
    assert feature.status != starting_stage


def test_delete_step_404s_for_an_unknown_step(app, client, db_session):
    user = _user(db_session, 'l')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.delete_feature_step', step_id=999999)
    resp = client.delete(url)
    assert resp.status_code == 404


# ── advance feature ─────────────────────────────────────────────────────

def test_advance_feature_moves_to_the_next_stage(app, client, db_session):
    user = _user(db_session, 'm')
    project = _project(db_session, 'm')
    feature = engine.create_feature(project, 'New thing')
    step = engine.add_step(feature, 'Only step')
    engine.tick_step(step, done=True)
    db_session.flush()
    starting_stage = feature.status
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.advance_feature', feature_id=feature.id)
    resp = client.post(url)

    assert resp.status_code == 200
    assert feature.status != starting_stage


def test_advance_feature_rejects_when_steps_are_not_done(app, client, db_session):
    user = _user(db_session, 'n')
    project = _project(db_session, 'n')
    feature = engine.create_feature(project, 'New thing')
    engine.add_step(feature, 'Not done yet')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.advance_feature', feature_id=feature.id)
    resp = client.post(url)
    assert resp.status_code == 400


def test_advance_feature_rejects_from_implementation(app, client, db_session):
    user = _user(db_session, 'o')
    project = _project(db_session, 'o')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.advance_feature', feature_id=feature.id)
    resp = client.post(url)
    assert resp.status_code == 400


def test_advance_feature_requires_auth(app, client, db_session):
    project = _project(db_session, 'p')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()

    with app.test_request_context():
        url = url_for('digital_innovation.advance_feature', feature_id=feature.id)
    resp = client.post(url)
    assert resp.status_code in (302, 401)


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
