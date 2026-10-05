"""Capability gates for Pre-Production, project files, site visits, DI and
time tracking, plus emulation-aware actor resolution.
"""
import pytest
from flask import session, url_for
from flask_login import login_user

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.core.shared.lib.capabilities import can, effective_user
from app.modules.core.shared.lib.org import LEGACY_ROLES
from app.modules.core.shared.lib.utils import get_actor
from app.modules.projects.routes.project_notes import _can_log_site_visit
from app.modules.digital_innovation.lib.access import (
    can_edit_di_board,
    can_view_di_performance,
)

ALL_ROLES = sorted(LEGACY_ROLES)


def _user(db_session, tag, role, team=None):
    user = User(name=f'Chunk5 {tag}', email=f'chunk5-{tag}@example.com', role=role, team=team)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


# ── Role tables ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('role', ALL_ROLES)
def test_complete_preproduction_matches_the_old_role_set(db_session, role):
    expected = role in ('designer', 'team_lead', 'admin', 'management')
    assert can('complete_preproduction', _user(db_session, f'pre-{role}', role)) is expected


@pytest.mark.parametrize('role', ALL_ROLES)
def test_manage_project_files_matches_the_old_role_set(db_session, role):
    expected = role in ('admin', 'cs', 'project_owner', 'management')
    assert can('manage_project_files', _user(db_session, f'files-{role}', role)) is expected


# ── Site visits: capability plus a team rule ───────────────────────────────

@pytest.mark.parametrize('role', ['admin', 'management', 'project_owner'])
def test_site_visits_open_to_the_capability_holders(db_session, role):
    assert _can_log_site_visit(_user(db_session, f'visit-{role}', role)) is True


def test_site_visits_are_team_scoped_for_designers(db_session):
    """Designers can log site visits only on the Technical team."""
    technical = _user(db_session, 'visit-tech', 'designer', team='Technical')
    other = _user(db_session, 'visit-2d', 'designer', team='2D')
    assert _can_log_site_visit(technical) is True
    assert _can_log_site_visit(other) is False


def test_read_only_roles_cannot_log_site_visits(db_session):
    for role in ('hr', 'production', 'logistics'):
        assert _can_log_site_visit(_user(db_session, f'visit-{role}', role)) is False


# ── Actor resolution ──────────────────────────────────────────────────────

def test_get_actor_resolves_to_the_emulated_user(app, db_session):
    """get_actor() and effective_user() both return the emulated user."""
    admin = _user(db_session, 'actor-admin', 'admin')
    designer = _user(db_session, 'actor-designer', 'designer')

    with app.test_request_context():
        login_user(admin)
        session['emulating_user_id'] = designer.id

        assert get_actor().id == designer.id
        assert effective_user().id == designer.id


def test_get_actor_is_the_logged_in_user_when_not_emulating(app, db_session):
    cs = _user(db_session, 'actor-plain', 'cs')
    with app.test_request_context():
        login_user(cs)
        assert get_actor().id == cs.id


# ── Digital Innovation stays emulation-aware ───────────────────────────────

def test_an_admin_emulating_a_designer_loses_di_board_editing(app, db_session):
    admin = _user(db_session, 'di-admin', 'admin')
    designer = _user(db_session, 'di-designer', 'designer')

    with app.test_request_context():
        login_user(admin)
        assert can_edit_di_board(admin) is True

        session['emulating_user_id'] = designer.id
        assert can_edit_di_board(admin) is False
        assert can_view_di_performance(admin) is False


def test_management_sees_di_performance_but_cannot_edit_the_board(app, db_session):
    boss = _user(db_session, 'di-mgmt', 'management')
    with app.test_request_context():
        login_user(boss)
        assert can_view_di_performance(boss) is True
        assert can_edit_di_board(boss) is False


# ── Time tracking ──────────────────────────────────────────────────────────

def test_time_tracking_is_gated_on_view_time_reports(app, client, db_session):
    login_as(client, app, _user(db_session, 'tt-designer', 'designer'), 'password123')
    with app.test_request_context():
        url = url_for('time_tracking.index')
    assert client.get(url).status_code == 403


def test_time_tracking_opens_for_management(app, client, db_session):
    login_as(client, app, _user(db_session, 'tt-mgmt', 'management'), 'password123')
    with app.test_request_context():
        url = url_for('time_tracking.index')
    assert client.get(url).status_code == 200
