"""
Access checks for Client Servicing. Every route gates through @require_cs,
never an inline role check. Role sets live in core/shared's capabilities map;
this file adds only the review lock, a temporary config switch.

The can_* helpers accept a None user and return False for it.
"""
from functools import wraps

from flask import abort, current_app

from app.modules.core.shared.lib.capabilities import can, effective_user


# The only roles let in while the review lock is on.
_REVIEW_ROLES = {'admin', 'management'}


def can_access_client_servicing(user):
    """True if `user` may use the Client Servicing page. Pass effective_user().
    While config CLIENT_SERVICING_REVIEW_ONLY is on, only _REVIEW_ROLES get in."""
    if not can('view_cs', user):
        return False
    if current_app.config.get('CLIENT_SERVICING_REVIEW_ONLY'):
        return getattr(user, 'role', None) in _REVIEW_ROLES
    return True


def can_view_finance(user):
    """True if `user` may see finance figures — money, invoicing, stuck.
    Page access is wider: project_owner can open CS but not see finance."""
    return can('view_finance', user)


def can_close_projects(user):
    """True if `user` may close a project or close out a cancelled one.
    Narrower than page access — project_owner and finance cannot close."""
    return can('close_projects', user)


def require_cs(f):
    """Gate a CS route on page access (review lock included); 403 otherwise.
    Emulation-aware: an admin previewing as someone is gated as them."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not can_access_client_servicing(effective_user()):
            abort(403)
        return f(*args, **kwargs)
    return decorated
