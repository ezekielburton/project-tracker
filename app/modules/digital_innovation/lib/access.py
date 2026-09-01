"""
app/modules/digital_innovation/lib/access.py

Single choke point for who can see Performance and Cost breakdown — every
route and template in those two surfaces gates through this one function,
never an inline role check. Boards stay open to everyone (no gate needed
there). When the Digital Innovation department gets its own role, adding
it here is the only change needed anywhere.
"""

_DI_PERFORMANCE_ROLES = {'admin', 'management'}


def can_view_di_performance(user):
    """True if `user` may view Performance / Cost breakdown. `user` is
    whatever current_user resolves to (a real User, or Flask-Login's
    AnonymousUserMixin when logged out — .role doesn't exist on that, so
    getattr with a default keeps this from ever raising)."""
    return getattr(user, 'role', None) in _DI_PERFORMANCE_ROLES