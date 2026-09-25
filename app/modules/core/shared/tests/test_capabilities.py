"""Coverage for the role to capability map and its helpers.

Locks down the role x capability table, the admin wildcard, emulation
awareness, both route decorators, and the dashboard's scoping fallback so a
role with no module of its own does not land on an empty page by accident.
"""
import pytest
from flask import session
from flask_login import login_user
from werkzeug.exceptions import Forbidden, Unauthorized

from app.modules.core.shared.models import User, Project
from app.modules.core.shared.lib.capabilities import (
    ADMIN_ONLY,
    ALL_CAPABILITIES,
    ROLE_CAPABILITIES,
    ROLE_LABELS,
    can,
    effective_user,
    require,
    require_api,
)
from app.modules.dashboard.lib.project_loader import scope_query


def _user(db_session, tag, role):
    user = User(name=f'Capability Test {tag}', email=f'cap-test-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, tag, cs_lead, status='in_progress'):
    project = Project(
        name=f'Capability Test Project {tag}',
        cs_lead_id=cs_lead.id,
        created_by_id=cs_lead.id,
        project_status=status,
    )
    db_session.add(project)
    db_session.flush()
    return project


# ── Map integrity ──────────────────────────────────────────────────────────

def test_every_granted_capability_is_recognised():
    for role, granted in ROLE_CAPABILITIES.items():
        unknown = {c for c in granted if c != '*'} - ALL_CAPABILITIES
        assert not unknown, f'{role} grants unrecognised capability {unknown}'


def test_every_capability_reaches_a_role():
    """A capability nobody holds is dead vocabulary. Admin's wildcard does not
    count, so anything only admin reaches has to say so in ADMIN_ONLY."""
    granted = set()
    for caps in ROLE_CAPABILITIES.values():
        granted |= {c for c in caps if c != '*'}
    assert ALL_CAPABILITIES - granted - ADMIN_ONLY == set()


def test_admin_only_capabilities_are_granted_to_nobody_else():
    for role, caps in ROLE_CAPABILITIES.items():
        if role == 'admin':
            continue
        assert not (caps & ADMIN_ONLY), f'{role} holds an admin-only capability'


def test_role_picker_matches_the_map():
    assert set(ROLE_LABELS) == set(ROLE_CAPABILITIES)


# ── The role x capability table ────────────────────────────────────────────

_TABLE = [
    # admin holds everything through the wildcard
    ('admin', 'admin_panel', True),
    ('admin', 'edit_finance', True),
    ('admin', 'view_time_reports', True),

    ('management', 'view_cs', True),
    ('management', 'view_finance', True),
    ('management', 'edit_finance', False),
    ('management', 'edit_invoicing_thresholds', True),
    ('management', 'switch_dashboard_scope', True),
    ('management', 'admin_panel', False),

    ('cs', 'view_cs', True),
    ('cs', 'edit_finance', True),
    ('cs', 'close_projects', True),
    ('cs', 'edit_invoicing_thresholds', False),
    ('cs', 'manage_projects', False),
    ('cs', 'admin_panel', False),

    ('finance', 'view_finance', True),
    ('finance', 'edit_finance', True),
    ('finance', 'close_projects', False),
    ('finance', 'view_all_projects', False),

    ('project_owner', 'view_cs', True),
    ('project_owner', 'view_finance', False),
    ('project_owner', 'create_projects', True),
    ('project_owner', 'close_projects', False),

    ('designer', 'manage_drafts', True),
    ('designer', 'claim_work', True),
    ('designer', 'view_cs', False),
    ('designer', 'view_all_projects', False),

    ('team_lead', 'manage_drafts', True),
    ('team_lead', 'view_finance', False),

    ('digital_innovation', 'view_all_di', True),
    ('digital_innovation', 'view_di_performance', False),
    ('digital_innovation', 'view_cs', False),

    # The three read-only roles: they see Projects and CS, they change nothing
    ('hr', 'view_cs', True),
    ('hr', 'view_finance', True),
    ('hr', 'view_all_projects', True),
    ('hr', 'edit_finance', False),
    ('hr', 'create_projects', False),
    ('hr', 'close_projects', False),
    ('hr', 'review_submissions', False),
    ('hr', 'transfer_projects', False),
    ('hr', 'raise_flags', False),
    ('hr', 'admin_panel', False),
    ('production', 'view_all_projects', True),
    ('production', 'create_projects', False),
    ('logistics', 'view_cs', True),
    ('logistics', 'edit_finance', False),
]


@pytest.mark.parametrize('role, capability, expected', _TABLE)
def test_capability_table(db_session, role, capability, expected):
    user = _user(db_session, f'{role}-{capability}', role)
    assert can(capability, user) is expected


def test_the_three_read_only_roles_hold_the_same_capabilities():
    assert ROLE_CAPABILITIES['hr'] == ROLE_CAPABILITIES['production'] == ROLE_CAPABILITIES['logistics']


def test_an_unknown_role_holds_nothing(db_session):
    user = _user(db_session, 'unknown', 'not_a_real_role')
    assert can('view_cs', user) is False
    assert can('admin_panel', user) is False


def test_a_user_without_a_role_holds_nothing(app):
    """An object with no .role holds nothing, an explicit None holds nothing,
    and neither does a logged-out visitor. Omitting the argument entirely is
    the only form that asks for the effective user."""
    assert can('view_cs', object()) is False
    assert can('view_cs', None) is False

    with app.test_request_context():
        assert can('view_cs') is False


# ── Emulation ──────────────────────────────────────────────────────────────

def test_an_admin_emulating_a_designer_gets_the_designers_capabilities(app, db_session):
    admin = _user(db_session, 'emu-admin', 'admin')
    designer = _user(db_session, 'emu-designer', 'designer')

    with app.test_request_context():
        login_user(admin)
        session['emulating_user_id'] = designer.id

        assert effective_user().id == designer.id
        assert can('manage_drafts') is True
        assert can('admin_panel') is False


def test_a_non_admin_cannot_emulate(app, db_session):
    designer = _user(db_session, 'emu-nonadmin', 'designer')
    admin = _user(db_session, 'emu-target-admin', 'admin')

    with app.test_request_context():
        login_user(designer)
        session['emulating_user_id'] = admin.id

        assert effective_user().id == designer.id
        assert can('admin_panel') is False


# ── Decorators ─────────────────────────────────────────────────────────────

@require('view_finance')
def _gated_page():
    return 'ok'


@require_api('view_finance')
def _gated_api():
    return {'success': True}


def test_require_allows_a_holder(app, db_session):
    with app.test_request_context():
        login_user(_user(db_session, 'req-cs', 'cs'))
        assert _gated_page() == 'ok'


def test_require_403s_without_the_capability(app, db_session):
    with app.test_request_context():
        login_user(_user(db_session, 'req-designer', 'designer'))
        with pytest.raises(Forbidden):
            _gated_page()


def test_require_401s_when_logged_out(app):
    with app.test_request_context():
        with pytest.raises(Unauthorized):
            _gated_page()


def test_require_api_allows_a_holder(app, db_session):
    with app.test_request_context():
        login_user(_user(db_session, 'api-cs', 'cs'))
        assert _gated_api() == {'success': True}


def test_require_api_returns_a_forbidden_body(app, db_session):
    with app.test_request_context():
        login_user(_user(db_session, 'api-designer', 'designer'))
        body, status = _gated_api()
        assert status == 403
        assert body.get_json() == {'success': False, 'error': 'Forbidden'}


def test_require_api_forbids_when_logged_out(app):
    with app.test_request_context():
        body, status = _gated_api()
        assert status == 403


# ── Dashboard scoping fallback ─────────────────────────────────────────────

def test_a_read_only_role_sees_every_active_project(app, db_session):
    cs = _user(db_session, 'scope-cs', 'cs')
    _project(db_session, 'one', cs)
    _project(db_session, 'two', cs)
    hr = _user(db_session, 'scope-hr', 'hr')

    assert scope_query(hr).count() >= 2


def test_a_role_without_project_visibility_sees_none(app, db_session):
    cs = _user(db_session, 'scope-cs-2', 'cs')
    _project(db_session, 'three', cs)
    finance = _user(db_session, 'scope-finance', 'finance')

    assert scope_query(finance).count() == 0
