"""Department and seniority to capability map, and the only helpers permission
checks go through. Routes call can() or the decorators, templates call the can()
Jinja global; neither knows how a capability is granted.
"""
from functools import wraps

from flask import abort, jsonify, session
from flask_login import current_user


# Every capability the app recognises. A grant outside this set is a typo, and
# test_capabilities.py fails on it.
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
    # HSE & Compliance
    'view_hse',
    'manage_hse',
    # The app shell. A role without it sees only its own module plus File
    # Storage and the Wiki.
    'view_workspace',
})


# Capabilities only admin holds. The capability tests fail if another role is
# granted one, so widening access takes an edit here too.
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


# Read-only access across Projects and Client Servicing, shared by the
# departments that have no module of their own.
_READ_ONLY_STAFF = {
    'view_workspace',
    'view_cs',
    'view_finance',
    'view_all_projects',
    'edit_client_directory',
}

_CLIENT_SERVICING = {
    'view_workspace',
    'view_cs', 'view_finance', 'edit_finance', 'close_projects',
    'view_all_projects', 'create_projects', 'review_submissions',
    'edit_client_directory', 'raise_flags',
    'manage_reference_data', 'manage_project_files',
}


# What each department may do (keys in core/shared/lib/org.py). Seniority adds
# to it; admin holds everything through User.is_admin.
DEPARTMENT_CAPABILITIES = {
    'client_servicing': set(_CLIENT_SERVICING),

    # Project owners stand in for CS when CS is stretched, so they hold all of
    # CS's capabilities plus their own.
    'project_owner': _CLIENT_SERVICING | {'log_site_visits', 'claim_ownership'},

    # Designers and leads share this set; what separates them is seniority and a
    # per-record rule (the deliverable's team), not a capability.
    'design': {
        'view_workspace',
        'manage_drafts', 'claim_work', 'raise_flags', 'complete_preproduction',
        'start_projects',
    },

    'finance': {
        'view_workspace',
        'view_cs', 'view_finance', 'edit_finance',
    },

    'digital_innovation': {
        'view_workspace',
        'view_all_di',
    },

    # No view_workspace: the officer sees only HSE, File Storage and the Wiki.
    # test_hse_sidebar.py fails if any other department lacks view_workspace.
    'hse': {
        'view_hse', 'manage_hse',
    },

    # HR also reads HSE (injuries and lost time are theirs too), so it can be
    # sent the HSE reports.
    'hr': set(_READ_ONLY_STAFF) | {'view_hse'},
    # Production and Logistics don't use Client Servicing.
    'production': set(_READ_ONLY_STAFF) - {'view_cs'},
    'logistics': set(_READ_ONLY_STAFF) - {'view_cs'},
}


# What each seniority level adds to the department's set.
SENIORITY_CAPABILITIES = {
    'none': set(),
    # Manager and Head of Department add nothing yet.
    'manager': set(),
    'head': set(),
    'management': {
        'view_workspace',
        'view_cs', 'view_finance', 'edit_invoicing_thresholds', 'close_projects',
        'view_all_projects', 'manage_projects', 'create_projects', 'start_projects',
        'review_submissions', 'edit_client_directory',
        'raise_flags', 'manage_flags', 'log_site_visits', 'manage_reference_data',
        'complete_preproduction', 'manage_project_files',
        'switch_dashboard_scope', 'view_team_snapshot',
        'view_di_performance', 'view_all_di',
        'view_hse',
        'write_friction_log',
        'view_time_reports',
    },
}


# Labels for the role keys in org.LEGACY_ROLES, in picker order. Read by pages
# not yet on the org model; the key picked is written through User.role.
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
    'hse': 'HSE Officer',
    'admin': 'Admin',
}

def role_label(value):
    """Role key to display label. Unknown values (e.g. a stored label) pass
    through unchanged."""
    value = (value or '').strip()
    return ROLE_LABELS.get(value, value)


def effective_user():
    """The user whose role governs: the emulated user while an admin views the
    app as someone else, otherwise the logged-in user. Safe when logged out.
    """
    from app.modules.core.shared.models import User

    emulating_id = session.get('emulating_user_id')
    if emulating_id and getattr(current_user, 'is_admin', False):
        return User.query.get(emulating_id) or current_user
    return current_user


# Distinguishes "no user argument given" from an explicit None, so a caller
# can hand over a possibly-missing user without guarding first.
_UNSET = object()


def capabilities_for(user):
    """Every capability `user` holds: '*' for admin, otherwise their department's
    set plus their seniority's. Empty for None or anything without org fields."""
    if getattr(user, 'is_admin', False):
        return frozenset({'*'})
    department = DEPARTMENT_CAPABILITIES.get(getattr(user, 'department', None), ())
    seniority = SENIORITY_CAPABILITIES.get(getattr(user, 'seniority', None), ())
    return frozenset(department) | frozenset(seniority)


def can(capability, user=_UNSET):
    """True if `user` holds `capability`. Omit `user` for the effective user;
    None (or anything without org fields) gets False. Admin holds everything.
    """
    granted = capabilities_for(effective_user() if user is _UNSET else user)
    return '*' in granted or capability in granted


def require(capability, real_user=False):
    """Gate an HTML route: 401 when logged out, 403 page without `capability`.

    real_user=True checks the logged-in user, not the emulated one, so admin
    tooling stays usable while previewing as someone else.
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
    """Gate a JSON route: a 403 {'success': False, 'error': 'Forbidden'} body for
    logged-out and under-privileged callers alike. real_user as in require().
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
