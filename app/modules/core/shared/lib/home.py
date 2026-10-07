"""Where a person starts, after login or on '/': the dashboard, or their own
module when they have no dashboard."""
from app.modules.core.shared.lib.capabilities import can


def home_endpoint(user):
    """The endpoint `user` starts on: HSE for someone who can open only HSE, otherwise the dashboard."""
    if not can('view_workspace', user) and can('view_hse', user):
        return 'hse.overview'
    return 'projects.index'
