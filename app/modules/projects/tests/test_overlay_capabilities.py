"""Coverage for the project-overlay and blog gates after the move to the map.

Two things are worth pinning. First, that each converted helper answers
identically to the role sets it replaced, for every role. Second — the reason
this chunk needed care — that the handful of role literals left in place stay
literal: they select a designer-only branch, and admin holds those capabilities
through the wildcard, so converting them would quietly let admin in.
"""
import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.core.shared.lib.capabilities import ROLE_CAPABILITIES, can
from app.modules.projects.routes.project_overlay._common import (
    _can_manage_deliverables,
    _can_manage_flags,
    _can_resolve_flag,
)
from app.modules.projects.routes.project_overlay.details import (
    _can_toggle_hold,
    _is_assigned_designer,
)

ALL_ROLES = sorted(ROLE_CAPABILITIES)


def _user(db_session, tag, role):
    user = User(name=f'Overlay Cap {tag}', email=f'overlay-cap-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


class _StubProject:
    """Enough of a Project for the permission helpers, which only read these."""
    def __init__(self, cs_lead_id=None, project_owner_id=None, created_by_id=None,
                 project_status='in_progress'):
        self.id = -1
        self.cs_lead_id = cs_lead_id
        self.project_owner_id = project_owner_id
        self.created_by_id = created_by_id
        self.project_status = project_status
        self.secondary_cs_assignments = []


class _StubUser:
    """A role is all can() reads."""
    def __init__(self, role):
        self.role = role


class _StubFlag:
    def __init__(self, created_by_id):
        self.created_by_id = created_by_id


# ── The role sets these helpers replaced ───────────────────────────────────

@pytest.mark.parametrize('role', ALL_ROLES)
def test_can_manage_flags_matches_the_old_role_set(db_session, role):
    expected = role in ('admin', 'cs', 'designer', 'team_lead', 'management')
    assert _can_manage_flags(_user(db_session, f'flags-{role}', role)) is expected


@pytest.mark.parametrize('role', ALL_ROLES)
def test_can_resolve_flag_matches_the_old_role_set(db_session, role):
    actor = _user(db_session, f'resolve-{role}', role)
    expected = role in ('admin', 'management')
    assert _can_resolve_flag(_StubFlag(created_by_id=-99), actor) is expected


def test_the_flags_creator_can_always_resolve_their_own(db_session):
    designer = _user(db_session, 'resolve-own', 'designer')
    assert _can_resolve_flag(_StubFlag(created_by_id=designer.id), designer) is True


@pytest.mark.parametrize('role', ALL_ROLES)
def test_toggle_hold_stays_admin_only(db_session, role):
    actor = _user(db_session, f'hold-{role}', role)
    assert _can_toggle_hold(_StubProject(), actor) is (role == 'admin')


def test_toggle_hold_still_allows_the_cs_lead(db_session):
    cs = _user(db_session, 'hold-lead', 'cs')
    assert _can_toggle_hold(_StubProject(cs_lead_id=cs.id), cs) is True


# ── Relationship rules keep their ownership half ───────────────────────────

def test_a_project_owner_manages_only_their_own_project(db_session):
    owner = _user(db_session, 'own-mine', 'project_owner')
    other = _user(db_session, 'own-other', 'project_owner')

    mine = _StubProject(project_owner_id=owner.id)
    assert _can_manage_deliverables(mine, owner) is True
    assert _can_manage_deliverables(mine, other) is False


def test_management_manages_a_project_it_owns_nothing_on(db_session):
    boss = _user(db_session, 'mgmt-any', 'management')
    assert _can_manage_deliverables(_StubProject(), boss) is True


def test_a_read_only_role_manages_nothing(db_session):
    for role in ('hr', 'production', 'logistics'):
        user = _user(db_session, f'ro-{role}', role)
        assert _can_manage_deliverables(_StubProject(), user) is False


# ── The literals that must not be converted ────────────────────────────────

def test_admin_holds_claim_work_through_the_wildcard(db_session):
    """The trap these next two tests guard against."""
    admin = _user(db_session, 'wildcard', 'admin')
    assert can('claim_work', admin) is True


def test_an_admin_is_not_an_assigned_designer(db_session):
    """Feeds the notification sweeps. Converting this check to can('claim_work')
    would make every admin count as assigned on every project."""
    admin = _user(db_session, 'assigned-admin', 'admin')
    cs = _user(db_session, 'assigned-cs', 'cs')
    assert _is_assigned_designer(None, admin) is False
    assert _is_assigned_designer(None, cs) is False


# ── Blog ───────────────────────────────────────────────────────────────────

def test_blog_editor_is_admin_only(app, client, db_session):
    user = _user(db_session, 'blog-designer', 'designer')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('blog.editor')
    assert client.get(url).status_code == 403


def test_blog_editor_opens_for_an_admin(app, client, db_session):
    user = _user(db_session, 'blog-admin', 'admin')
    login_as(client, app, user, 'password123')

    with app.test_request_context():
        url = url_for('blog.editor')
    assert client.get(url).status_code == 200


# ── Start Project ──────────────────────────────────────────────────────────

@pytest.mark.parametrize('role', ALL_ROLES)
def test_only_design_management_and_admin_can_start_a_project(role):
    """CS deliberately lost this: Start Project used to run on a relationship
    check that included the CS lead. The people doing the work start it now."""
    expected = role in ('designer', 'team_lead', 'management', 'admin')
    assert can('start_projects', _StubUser(role)) is expected
