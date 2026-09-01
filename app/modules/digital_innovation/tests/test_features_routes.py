"""Route-level coverage for Digital Innovation feature creation and the
read-only feature detail view."""
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject, DiFeature, DI_STAGES
from app.modules.digital_innovation.lib import step_engine as engine


def _user(db_session, tag, role='admin'):
    user = User(name='Test User', email=f'di-route-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, tag, lifecycle='active'):
    project = DiProject(name=f'Test DI Project {tag}', lifecycle=lifecycle)
    db_session.add(project)
    db_session.flush()
    return project


def test_create_feature_requires_auth(app, client, db_session):
    project = _project(db_session, 'a')
    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': 'New thing'})
    assert resp.status_code in (302, 401)


def test_create_feature_happy_path(app, client, db_session):
    user = _user(db_session, 'b')
    project = _project(db_session, 'b')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': 'New thing', 'projected_date': '2026-09-15'})

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['name'] == 'New thing'
    assert body['status'] == DI_STAGES[0]

    feature = DiFeature.query.get(body['id'])
    assert feature is not None
    assert feature.di_project_id == project.id
    assert feature.projected_date.isoformat() == '2026-09-15'


def test_create_feature_without_a_date_is_fine(app, client, db_session):
    user = _user(db_session, 'c')
    project = _project(db_session, 'c')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': 'New thing'})

    assert resp.status_code == 201
    feature = DiFeature.query.get(resp.get_json()['id'])
    assert feature.projected_date is None


def test_create_feature_requires_a_name(app, client, db_session):
    user = _user(db_session, 'd')
    project = _project(db_session, 'd')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': '   '})

    assert resp.status_code == 400
    assert DiFeature.query.filter_by(di_project_id=project.id).count() == 0


def test_create_feature_rejects_a_bad_date(app, client, db_session):
    user = _user(db_session, 'e')
    project = _project(db_session, 'e')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': 'New thing', 'projected_date': 'not-a-date'})

    assert resp.status_code == 400


def test_create_feature_404s_for_an_unknown_project(app, client, db_session):
    user = _user(db_session, 'f')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=999999)
    resp = client.post(url, json={'name': 'New thing'})

    assert resp.status_code == 404


def test_create_feature_404s_for_an_archived_project(app, client, db_session):
    user = _user(db_session, 'g')
    project = _project(db_session, 'g', lifecycle='archived')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.create_feature', di_project_id=project.id)
    resp = client.post(url, json={'name': 'New thing'})

    assert resp.status_code == 404


def test_feature_detail_requires_auth(app, client, db_session):
    project = _project(db_session, 'h')
    feature = engine.create_feature(project, 'New thing')
    db_session.flush()

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_feature_detail_shows_name_and_status_row(app, client, db_session):
    user = _user(db_session, 'i')
    project = _project(db_session, 'i')
    feature = engine.create_feature(project, 'Homepage redesign')
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Homepage redesign' in body
    assert project.name in body
    assert 'Researching' in body  # first stage's label, in the status row


def test_feature_detail_404s_for_an_unknown_feature(app, client, db_session):
    user = _user(db_session, 'j')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=999999)
    resp = client.get(url)
    assert resp.status_code == 404


def test_feature_detail_shows_closed_note_for_a_closed_feature(app, client, db_session):
    user = _user(db_session, 'k')
    project = _project(db_session, 'k')
    feature = engine.create_feature(project, 'Old thing')
    feature.status = DI_STAGES[-1]
    engine.close_feature(feature)
    db_session.flush()
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Closed' in body
