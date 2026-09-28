"""All Digital Innovation access checks. Routes and templates gate through
these; the role grants live in core/shared/lib/capabilities.py.

Every check is emulation-aware: when an admin emulates someone, the emulated
user's role governs (see _effective_role_user).
"""
from app.modules.core.shared.lib.capabilities import can


def _effective_role_user(user):
    """The emulated user when `user` is an admin who is emulating, else
    `user`. Safe for an anonymous user."""
    from flask import session
    from app.modules.core.shared.models import User

    emulating_id = session.get('emulating_user_id')
    if emulating_id and getattr(user, 'role', None) == 'admin':
        return User.query.get(emulating_id) or user
    return user


def can_view_di_performance(user):
    """True if `user` may view Performance / Cost breakdown / the feature-detail
    cost note. Safe when logged out."""
    return can('view_di_performance', _effective_role_user(user))


def can_view_di_project(user, project):
    """True if `user` may view `project` (board, features, archive entry).
    Everyone sees the permanent OVP board; other boards need view_all_di."""
    if project is not None and getattr(project, 'is_permanent', False):
        return True
    return can('view_all_di', _effective_role_user(user))


def visible_di_projects(user, projects):
    """The DiProjects `user` may see, in the same order."""
    return [p for p in projects if can_view_di_project(user, p)]


def can_edit_di_templates(user):
    """True if `user` may view and edit the step-templates screen."""
    return can('manage_di_templates', _effective_role_user(user))


def can_edit_di_board(user):
    """True if `user` may change board data: projects, features, steps and
    the Incoming tray. Viewing is gated separately by can_view_di_project."""
    return can('edit_di_board', _effective_role_user(user))
