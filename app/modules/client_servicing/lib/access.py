"""
Single choke point for who can see the Client Servicing page — every route
gates through this, never an inline role check. Same pattern as the
Digital Innovation module's access.py. When CS gets its own role, adding
it here is the only change needed anywhere.
"""
from flask import session
from flask_login import current_user

_CLIENT_SERVICING_ROLES = {
    'admin',
    'management',
    'cs',
    'project_owner',
    'finance',
}


def _effective_user():
    """Emulation-aware actor: the emulated user when an admin is viewing
    the app as someone else (session['emulating_user_id']), otherwise the
    logged-in user. The access check, saved layout, and edit attribution
    all resolve identity through this. The admin-only Scope CRUD in
    scopes_admin.py stays on current_user, so an admin previewing as
    someone else keeps real admin tools."""
    from app.modules.core.shared.models import User
    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        return User.query.get(emulating_id)
    return current_user


def can_access_client_servicing(user):
    """True if `user` may view/use the Client Servicing page. Pass the
    _effective_user() result; getattr guards the logged-out case, which
    has no .role."""
    return getattr(user, 'role', None) in _CLIENT_SERVICING_ROLES
