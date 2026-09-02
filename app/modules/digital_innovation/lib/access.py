"""
app/modules/digital_innovation/lib/access.py

Single choke point for who can see Performance, Cost breakdown, and any
other cost/charge/profit-adjacent surface (e.g. the feature detail
modal's footer note) — every route and template showing that kind of
information gates through this one function, never an inline role check.
Boards stay open to everyone (no gate needed there). When the Digital
Innovation department gets its own role, or a surface needs a different
role set than the others, adding/splitting it here is the only change
needed anywhere.

Emulation-aware: when a real admin is emulating another user (session[
'emulating_user_id'], set by admin/routes/admin.py), every check here
goes by the emulated person's role, not the admin's own — the same
pattern used throughout the app (core/shared/lib/utils.py's get_actor(),
core/shared/routes/api.py's _effective_user(), app/__init__.py's
inject_effective_user() context processor, etc.). That resolution lives
in _effective_role_user() below, called once from inside
can_view_di_performance() — callers just pass current_user and always
get the right answer, whether or not an admin is currently emulating
someone, with nothing to remember at the call site.
"""

_DI_PERFORMANCE_ROLES = {'admin', 'management'}


def _effective_role_user(user):
    """The user whose role actually governs DI visibility — the person a
    real admin is currently emulating, if any, otherwise `user` itself.
    Only ever swaps in the emulated user when `user` is genuinely an
    admin (emulation is admin-only elsewhere in the app too), so this is
    safe to call with a logged-out AnonymousUserMixin as well."""
    from flask import session
    from app.modules.core.shared.models import User

    emulating_id = session.get('emulating_user_id')
    if emulating_id and getattr(user, 'role', None) == 'admin':
        return User.query.get(emulating_id) or user
    return user


def can_view_di_performance(user):
    """True if `user` may view Performance / Cost breakdown / the feature
    detail footer's cost note. `user` is whatever current_user resolves
    to (a real User, or Flask-Login's AnonymousUserMixin when logged
    out — .role doesn't exist on that, so getattr with a default keeps
    this from ever raising)."""
    effective = _effective_role_user(user)
    return getattr(effective, 'role', None) in _DI_PERFORMANCE_ROLES


# Deliberately its own set, not reused from _DI_PERFORMANCE_ROLES, even
# though today it's a subset (admin only, not management) — per Ezekiel,
# so the two can be widened or narrowed independently later without one
# change accidentally affecting the other.
_DI_TEMPLATE_EDIT_ROLES = {'admin'}


def can_edit_di_templates(user):
    """True if `user` may view/edit the department-wide step templates
    screen (Edit Templates — routes/templates.py). Same emulation-aware
    resolution as can_view_di_performance: if a real admin is emulating
    someone else, the emulated person's role is what counts."""
    effective = _effective_role_user(user)
    return getattr(effective, 'role', None) in _DI_TEMPLATE_EDIT_ROLES


# The board itself (viewing a project, opening a feature) stays open to
# every logged-in user — only actually CHANGING something is gated: new
# projects/features, ticking/adding/deleting a step, advancing, closing.
# "Me and my future team" per Ezekiel (28 Aug 2026) — starts admin-only,
# same as _DI_TEMPLATE_EDIT_ROLES and deliberately its own set rather than
# reused from it, so as his team grows, adding their role(s) here is the
# one change needed, independent of who can edit templates.
_DI_BOARD_WRITE_ROLES = {'admin'}


def can_edit_di_board(user):
    """True if `user` may create a project/feature, or tick, add, delete,
    advance or close a feature's steps — every DI action that changes
    data rather than just viewing it. Same emulation-aware resolution as
    the other checks here: if a real admin is emulating someone else, the
    emulated person's role is what counts — so emulating a designer
    genuinely previews the read-only experience they get."""
    effective = _effective_role_user(user)
    return getattr(effective, 'role', None) in _DI_BOARD_WRITE_ROLES
