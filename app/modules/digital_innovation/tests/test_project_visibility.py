"""Coverage for the project *visibility* gate (can_view_di_project /
visible_di_projects, lib/access.py) — every project except the permanent
OVP board is restricted to admin, management and the future
digital_innovation role. This is a separate
gate from can_edit_di_board (test_board_write_access.py covers that one):
a role can fail visibility and never even reach the write-gate question,
since there's nothing to view in the first place.

Every other DI test file that builds a non-permanent project for a
restricted role now stands in for OVP via is_permanent=True so it can
still isolate whatever *that* file is actually testing — this file is
where the visibility rule itself gets exercised directly, at both the
unit level (can_view_di_project, visible_di_projects) and the route
level (project_board, board_columns_fragment, feature_detail)."""
from flask import url_for

from app.modules.core.shared.testing import login_as
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.lib.access import can_view_di_project, visible_di_projects
from app.modules.digital_innovation.tests.test_features_routes import _user
from app.modules.digital_innovation.tests.test_feature_steps_routes import _project


# ── can_view_di_project (unit level) ─────────────────────────────────────

def test_can_view_di_project_is_true_for_any_role_on_the_permanent_project(db_session):
    ovp = _project(db_session, 'a', is_permanent=True)
    for role in ('designer', 'cs', 'team_lead', 'project_owner', 'management', 'admin'):
        user = _user(db_session, f'a-{role}', role=role)
        assert can_view_di_project(user, ovp) is True


def test_can_view_di_project_is_true_for_every_allowed_role_on_a_non_permanent_project(app, db_session):
    project = _project(db_session, 'b')
    with app.test_request_context():
        for role in ('admin', 'management', 'digital_innovation'):
            # 'digital_innovation' isn't a registerable role yet; role is a
            # free-text column, so this exercises the gate as it will behave
            # once that role exists.
            user = _user(db_session, f'b-{role}', role=role)
            assert can_view_di_project(user, project) is True


def test_can_view_di_project_is_false_for_every_other_role_on_a_non_permanent_project(app, db_session):
    project = _project(db_session, 'c')
    with app.test_request_context():
        for role in ('designer', 'cs', 'team_lead', 'project_owner'):
            user = _user(db_session, f'c-{role}', role=role)
            assert can_view_di_project(user, project) is False


def test_can_view_di_project_is_emulation_aware(app, db_session):
    # Same swap every other gate in lib/access.py relies on: a real admin
    # emulating a designer should see exactly what that designer sees.
    # _effective_role_user reads session['emulating_user_id'] directly, so
    # this needs a request context with that key set rather than a bare
    # function call — the app fixture is the same Flask app the route-
    # level tests below use via the test client.
    from flask import session
    project = _project(db_session, 'd')
    admin = _user(db_session, 'd', role='admin')
    designer = _user(db_session, 'd2', role='designer')

    with app.test_request_context():
        assert can_view_di_project(admin, project) is True  # admin's own role
        session['emulating_user_id'] = designer.id
        assert can_view_di_project(admin, project) is False


def test_can_view_di_project_ignores_emulation_from_a_non_admin(app, db_session):
    # Only real admins can emulate elsewhere in the app — a stray
    # emulating_user_id on a non-admin's session should be ignored, same
    # as every other gate here.
    from flask import session
    project = _project(db_session, 'e')
    management = _user(db_session, 'e', role='management')
    designer = _user(db_session, 'e2', role='designer')

    with app.test_request_context():
        session['emulating_user_id'] = designer.id
        assert can_view_di_project(management, project) is True


# ── visible_di_projects (unit level) ─────────────────────────────────────

def test_visible_di_projects_keeps_only_permanent_projects_for_a_restricted_role(app, db_session):
    ovp = _project(db_session, 'f', is_permanent=True)
    other = _project(db_session, 'g')
    user = _user(db_session, 'f', role='designer')

    with app.test_request_context():
        assert visible_di_projects(user, [ovp, other]) == [ovp]


def test_visible_di_projects_keeps_every_project_in_order_for_an_allowed_role(app, db_session):
    ovp = _project(db_session, 'h', is_permanent=True)
    other = _project(db_session, 'i')
    user = _user(db_session, 'h', role='management')

    with app.test_request_context():
        assert visible_di_projects(user, [other, ovp]) == [other, ovp]


# ── project_board (route level) ──────────────────────────────────────────

def test_project_board_403s_for_a_project_owner_on_a_non_permanent_project(app, client, db_session):
    project = _project(db_session, 'j')
    user = _user(db_session, 'j', role='project_owner')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 403


def test_project_board_200s_for_management_on_a_non_permanent_project(app, client, db_session):
    project = _project(db_session, 'k')
    user = _user(db_session, 'k', role='management')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 200


def test_project_board_sidebar_shows_only_ovp_to_a_restricted_role(app, client, db_session):
    ovp = _project(db_session, 'l', is_permanent=True)
    _project(db_session, 'm')  # a second, non-permanent board
    user = _user(db_session, 'l', role='designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.project_board', di_project_id=ovp.id)
    resp = client.get(url)
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'Test DI Project l' in body
    assert 'Test DI Project m' not in body


# ── board_columns_fragment (route level) ─────────────────────────────────

def test_board_columns_fragment_403s_for_a_team_lead_on_a_non_permanent_project(app, client, db_session):
    project = _project(db_session, 'n')
    user = _user(db_session, 'n', role='team_lead')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.board_columns_fragment', project_id=project.id)
    resp = client.get(url)

    assert resp.status_code == 403


# ── feature_detail (route level) ─────────────────────────────────────────

def test_feature_detail_403s_for_a_cs_role_on_a_non_permanent_projects_feature(app, client, db_session):
    project = _project(db_session, 'o')
    feature = engine.create_feature(project, 'New thing')
    user = _user(db_session, 'o', role='cs')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)

    assert resp.status_code == 403


def test_feature_detail_200s_for_admin_on_a_non_permanent_projects_feature(app, client, db_session):
    project = _project(db_session, 'p')
    feature = engine.create_feature(project, 'New thing')
    user = _user(db_session, 'p', role='admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('digital_innovation.feature_detail', feature_id=feature.id)
    resp = client.get(url)

    assert resp.status_code == 200
