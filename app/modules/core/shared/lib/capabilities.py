"""Role to capability map, and the only helpers permission checks go through.

One dict decides what each role may do; routes call can() or the decorators,
templates call the can() Jinja global. Adding a role means adding one key here.
"""
from functools import wraps

from flask import abort, jsonify, session
from flask_login import current_user


# Every capability the app recognises. A grant naming anything outside this set
# is a typo, and the unit table fails on it.
ALL_CAPABILITIES = frozenset({
    # Admin surfaces
    'admin_panel',
    'manage_users',
    'manage_wiki',
    'manage_blog',
    'manage_feedback',
    'manage_achievements',
    'manage_scopes',
    'manage_di_templates',
    # Client Servicing and finance
    'view_cs',
    'close_projects',
    'view_finance',
    'edit_finance',
    'edit_invoicing_thresholds',
    # Projects
    'view_all_projects',
    'manage_projects',
    'create_projects',
    'start_projects',
    'toggle_project_hold',
    'claim_ownership',
    'complete_preproduction',
    'manage_project_files',
    'override_status',
    'review_submissions',
    'manage_drafts',
    'claim_work',
    'transfer_projects',
    'edit_client_directory',
    'raise_flags',
    'manage_flags',
    'log_site_visits',
    'manage_reference_data',
    # Dashboard
    'switch_dashboard_scope',
    'view_team_snapshot',
    # Digital Innovation
    'view_di_performance',
    'view_all_di',
    'edit_di_board',
    # Signal tray
    'write_friction_log',
    # Time tracking
    'view_time_reports',
})


# Capabilities no role but admin holds today. Listed so that granting one to a
# role is a deliberate edit in two places, not a silent widening.
ADMIN_ONLY = frozenset({
    'admin_panel',
    'manage_users',
    'manage_wiki',
    'manage_blog',
    'manage_feedback',
    'manage_achievements',
    'manage_scopes',
    'manage_di_templates',
    'override_status',
    'edit_di_board',
    'toggle_project_hold',
})


# Read-only across Projects and Client Servicing. Shared by the roles whose own
# modules do not exist yet, so their access widens in one place later.
_READ_ONLY_STAFF = {
    'view_cs',
    'view_finance',
    'view_all_projects',
    'edit_client_directory',
}


ROLE_CAPABILITIES = {
    'admin': {'*'},

    'management': {
        'view_cs', 'view_finance', 'edit_invoicing_thresholds', 'close_projects',
        'view_all_projects', 'manage_projects', 'create_projects', 'start_projects',
        'review_submissions', 'transfer_projects', 'edit_client_directory',
        'raise_flags', 'manage_flags', 'log_site_visits', 'manage_reference_data',
        'complete_preproduction', 'manage_project_files',
        'switch_dashboard_scope', 'view_team_snapshot',
        'view_di_performance', 'view_all_di',
        'write_friction_log',
        'view_time_reports',
    },

    'cs': {
        'view_cs', 'view_finance', 'edit_finance', 'close_projects',
        'view_all_projects', 'create_projects', 'review_submissions',
        'transfer_projects', 'edit_client_directory', 'raise_flags',
        'manage_reference_data', 'manage_project_files',
    },

    'finance': {
        'view_cs', 'view_finance', 'edit_finance',
    },

    'project_owner': {
        'view_cs', 'view_all_projects', 'create_projects', 'log_site_visits',
        'claim_ownership',
    },

    # Designer and team_lead hold the same capabilities; what separates them is
    # the team a deliverable belongs to, which is a per-record rule, not a role.
    'designer': {
        'manage_drafts', 'claim_work', 'raise_flags', 'complete_preproduction',
        'start_projects',
    },
    'team_lead': {
        'manage_drafts', 'claim_work', 'raise_flags', 'complete_preproduction',
        'start_projects',
    },

    'digital_innovation': {
        'view_all_di',
    },

    'hr': set(_READ_ONLY_STAFF),
    'production': set(_READ_ONLY_STAFF),
    'logistics': set(_READ_ONLY_STAFF),
}


# Role picker options, in display order. The value is what lands in User.role.
ROLE_LABELS = {
    'cs': 'Client Servicing',
    'designer': 'Designer',
    'team_lead': 'Team Lead',
    'management': 'Management',
    'project_owner': 'Project Owner',
    'finance': 'Finance',
    'digital_innovation': 'Digital Innovation',
    'hr': 'HR',
    'production': 'Production',
    'logistics': 'Logistics',
    'admin': 'Admin',
}


def effective_user():
    """The user whose role governs — the emulated user when an admin is viewing
    the app as someone else, otherwise the logged-in user. Safe when logged out.
    """
    from app.modules.core.shared.models import User

    emulating_id = session.get('emulating_user_id')
    if emulating_id and getattr(current_user, 'role', None) == 'admin':
        return User.query.get(emulating_id) or current_user
    return current_user


# Distinguishes "no user argument given" from an explicit None, so a caller
# can hand over a possibly-missing user without guarding first.
_UNSET = object()


def can(capability, user=_UNSET):
    """True if `user` holds `capability`. Omit `user` for the effective user;
    pass None (or anything without a role) and the answer is False. Admin's
    '*' grants everything.
    """
    actor = effective_user() if user is _UNSET else user
    granted = ROLE_CAPABILITIES.get(getattr(actor, 'role', None), frozenset())
    return '*' in granted or capability in granted


def require(capability, real_user=False):
    """Gate an HTML route: 401 when logged out, 403 page without `capability`.

    real_user=True checks the logged-in user instead of the emulated one — for
    admin-only tooling an admin should keep while previewing as someone else.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not can(capability, current_user if real_user else effective_user()):
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def require_api(capability, real_user=False):
    """Gate a JSON route: a 403 Forbidden body, the shape the admin API already
    returns, for both logged-out and under-privileged callers. real_user as in
    require().
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            actor = current_user if real_user else effective_user()
            if not current_user.is_authenticated or not can(capability, actor):
                return jsonify({'success': False, 'error': 'Forbidden'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
