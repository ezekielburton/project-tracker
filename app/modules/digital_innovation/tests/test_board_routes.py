"""Tests for routes/board.py board_columns_fragment, the live-refresh
fragment. The full board page is covered by other route tests."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project as _lifecycle_project


def test_board_columns_fragment_requires_auth(app, client, db_session):
    project = _lifecycle_project(db_session, 'ba')

    with app.test_request_context():
        url = url_for('digital_innovation.board_columns_fragment', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_board_columns_fragment_shows_open_features(app, client, db_session):
    project = _lifecycle_project(db_session, 'bb')
    engine.create_feature(project, 'Homepage redesign')
    user = _user(db_session, 'bb', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.board_columns_fragment', project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-board-body' in body
    assert 'Homepage redesign' in body


def test_board_columns_fragment_works_for_a_read_only_viewer(app, client, db_session):
    # Viewing needs no can_edit_board. is_permanent=True so a designer passes
    # can_view_di_project (tested in test_project_visibility.py).
    project = _lifecycle_project(db_session, 'bc', is_permanent=True)
    engine.create_feature(project, 'Viewer-visible feature')
    user = _user(db_session, 'bc', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.board_columns_fragment', project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Viewer-visible feature' in body
    # A designer can't add features, so the control is not rendered.
    assert 'di-add-feature-trigger' not in body


def test_board_columns_fragment_shows_closed_features(app, client, db_session):
    project = _lifecycle_project(db_session, 'bd')
    feature = engine.create_feature(project, 'Done thing')
    engine.close_feature(feature)
    user = _user(db_session, 'bd', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.board_columns_fragment', project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Done thing' in body


def test_board_columns_fragment_404s_for_an_unknown_project(app, client, db_session):
    user = _user(db_session, 'be', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.board_columns_fragment', project_id=999999)
    resp = client.get(url)
    assert resp.status_code == 404


def test_board_columns_fragment_404s_for_a_closed_project(app, client, db_session):
    project = DiProject(name='Closed project', lifecycle='closed')
    db_session.add(project)
    db_session.flush()
    user = _user(db_session, 'bf', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.board_columns_fragment', project_id=project.id)
    resp = client.get(url)
    assert resp.status_code == 404


def test_board_index_serves_the_trailing_slash_url(app, client, db_session):
    # /digital-innovation/ must reach the board, not 404, so an old link or
    # bookmark with the slash still lands somewhere real.
    _lifecycle_project(db_session, 'slash', is_permanent=True)
    user = _user(db_session, 'slash', role='admin')
    login_as(client, app, user, 'password123')

    for url in ('/digital-innovation', '/digital-innovation/'):
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert 'di-board' in resp.get_data(as_text=True)
