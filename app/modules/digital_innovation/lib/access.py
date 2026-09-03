"""Single choke point for Digital Innovation access: who may view Performance
and cost surfaces, who may view a given project, and who may edit boards or
templates. Routes and templates gate through these functions instead of inline
role checks, so widening a role set is a one-line change here.

All checks are emulation-aware — when an admin emulates another user, the
emulated person's role governs, resolved once in _effective_role_user()."""

_DI_PERFORMANCE_ROLES = {'admin', 'management'}


def _effective_role_user(user):
    """The user whose role governs DI access — the emulated user when an admin
    is emulating, else `user`. Only swaps when `user` is genuinely an admin;
    safe for a logged-out AnonymousUserMixin."""
    from flask import session
    from app.modules.core.shared.models import User

    emulating_id = session.get('emulating_user_id')
    if emulating_id and getattr(user, 'role', None) == 'admin':
        return User.query.get(emulating_id) or user
    return user


def can_view_di_performance(user):
    """True if `user` may view Performance / Cost breakdown / the feature-detail
    cost note. Safe when logged out (getattr guards the missing .role)."""
    effective = _effective_role_user(user)
    return getattr(effective, 'role', None) in _DI_PERFORMANCE_ROLES


# Own set (not reused from _DI_PERFORMANCE_ROLES) so project visibility can be
# widened or narrowed independently of who can see Performance/Cost.
_DI_PROJECT_VISIBILITY_ROLES = {'admin', 'digital_innovation', 'management'}


def can_view_di_project(user, project):
    """True if `user` may view `project` — its board, features, archive entry.
    Every DiProject is restricted to _DI_PROJECT_VISIBILITY_ROLES; everyone else
    sees only the permanent OVP board (project.is_permanent). Emulation-aware."""
    if project is not None and getattr(project, 'is_permanent', False):
        return True
    effective = _effective_role_user(user)
    return getattr(effective, 'role', None) in _DI_PROJECT_VISIBILITY_ROLES


def visible_di_projects(user, projects):
    """Filter DiProject rows to those `user` may see, preserving order. Use for
    any sidebar/list surface instead of a per-template role check."""
    return [p for p in projects if can_view_di_project(user, p)]


# Own set so template-edit access can change independently of the others.
_DI_TEMPLATE_EDIT_ROLES = {'admin'}


def can_edit_di_templates(user):
    """True if `user` may view/edit the department step-templates screen.
    Emulation-aware."""
    effective = _effective_role_user(user)
    return getattr(effective, 'role', None) in _DI_TEMPLATE_EDIT_ROLES


# Viewing a board/feature stays open to every logged-in user; only data
# changes are gated. Own set so the team's role(s) can be added here later,
# independently of who can edit templates.
_DI_BOARD_WRITE_ROLES = {'admin'}


def can_edit_di_board(user):
    """True if `user` may change DI data — create a project/feature, or tick,
    add, delete, advance or close a feature's steps. Viewing stays open to all;
    only writes are gated. Emulation-aware."""
    effective = _effective_role_user(user)
    return getattr(effective, 'role', None) in _DI_BOARD_WRITE_ROLES
