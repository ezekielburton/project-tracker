"""Route-level coverage for the Archive screen (routes/archive.py) and
the sidebar's project-lifecycle surfaces: the per-project Close button
(board.html/_sidebar.html) and the Archive screen's Reopen/Archive
buttons. The lifecycle state changes themselves (close/archive/reopen)
have their own coverage in test_project_routes.py — these tests are
about what gets rendered, and to whom."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.models import DiProject
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project


def test_archive_screen_requires_auth(app, client, db_session):
    with app.test_request_context():
        url = url_for('digital_innovation.archive_screen')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_archive_screen_lists_closed_and_archived_projects(app, client, db_session):
    _project(db_session, 'aa', lifecycle='closed')
    _project(db_session, 'ab', lifecycle='archived')
    _project(db_session, 'ac')  # active — appears in the sidebar's project
    # switcher (every DI screen includes it), just not in either archive
    # list — so the assertion below checks the archive-row markup
    # specifically, not the page as a whole.
    user = _user(db_session, 'aa', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.archive_screen')
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert '<span class="di-archive-name">Test DI Project aa</span>' in body
    assert '<span class="di-archive-name">Test DI Project ab</span>' in body
    assert '<span class="di-archive-name">Test DI Project ac</span>' not in body


def test_archive_screen_shows_actions_to_an_admin(app, client, db_session):
    _project(db_session, 'ad0')  # an active project — needed so the
    # sidebar's default_project() lookup (used when a screen isn't
    # scoped to one project) has something to find.
    _project(db_session, 'ad', lifecycle='closed')
    _project(db_session, 'ae', lifecycle='archived')
    user = _user(db_session, 'ad', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.archive_screen')
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-archive-reopen-btn' in body
    assert 'di-archive-archive-btn' in body


def test_archive_screen_hides_actions_from_a_designer(app, client, db_session):
    _project(db_session, 'af0')  # active — see the comment above
    _project(db_session, 'af', lifecycle='closed')
    _project(db_session, 'ag', lifecycle='archived')
    user = _user(db_session, 'af', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.archive_screen')
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    # The projects themselves are still visible — only the buttons are gated.
    assert 'Test DI Project af' in body
    assert 'di-archive-reopen-btn' not in body
    assert 'di-archive-archive-btn' not in body


def test_archive_screen_hides_actions_from_an_admin_emulating_a_designer(app, client, db_session):
    _project(db_session, 'ah0')  # active — see the comment above
    _project(db_session, 'ah', lifecycle='closed')
    admin = _user(db_session, 'ah', role='admin')
    designer = _user(db_session, 'ah2', role='designer')
    login_as(client, app, admin, 'password123')

    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    with app.test_request_context():
        url = url_for('digital_innovation.archive_screen')
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-archive-reopen-btn' not in body


# ── sidebar's Close control ──────────────────────────────────────────────

def test_board_shows_close_button_for_editable_projects_to_an_admin(app, client, db_session):
    project = _project(db_session, 'ai')
    user = _user(db_session, 'ai', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-project-close-btn' in body


def test_board_hides_close_button_from_a_designer(app, client, db_session):
    project = _project(db_session, 'aj')
    user = _user(db_session, 'aj', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-project-close-btn' not in body


def test_board_never_shows_close_button_for_the_permanent_project(app, client, db_session):
    permanent = DiProject(name='OVP', lifecycle='active', is_permanent=True)
    db_session.add(permanent)
    db_session.flush()
    user = _user(db_session, 'ak', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=permanent.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'di-project-close-btn' not in body


def test_board_sidebar_excludes_closed_and_archived_projects(app, client, db_session):
    active_project = _project(db_session, 'al')
    _project(db_session, 'am', lifecycle='closed')
    _project(db_session, 'an', lifecycle='archived')
    user = _user(db_session, 'al', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=active_project.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Test DI Project al' in body
    assert 'Test DI Project am' not in body
    assert 'Test DI Project an' not in body
