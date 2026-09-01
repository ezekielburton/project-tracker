"""
Single choke point for who can see the Client Servicing page — every route
gates through this, never an inline role check. Same pattern as the
Digital Innovation module's access.py. When CS gets its own role, adding
it here is the only change needed anywhere.
"""

_CLIENT_SERVICING_ROLES = {'admin', 'management', 'cs'}


def can_access_client_servicing(user):
    """True if `user` may view/use the Client Servicing page. `user` is
    whatever current_user resolves to (a real User, or Flask-Login's
    AnonymousUserMixin when logged out — .role doesn't exist on that, so
    getattr with a default keeps this from ever raising)."""
    return getattr(user, 'role', None) in _CLIENT_SERVICING_ROLES
