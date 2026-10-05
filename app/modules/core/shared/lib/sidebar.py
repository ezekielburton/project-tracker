"""Which sidebar links each person sees.

Client Servicing and HSE hide themselves through their own access checks in
base.html. This file covers the rest: pages not built yet (admin only) and
links a department can open but doesn't need. Hiding here is tidy-up, not security.
"""
from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.core.shared.lib.org import is_management


# Pages not built yet. Only admin sees them.
UNBUILT = frozenset({'color-directory', 'production-directory', 'birthday-calendar'})

_STOCK = {'magnific', 'shutterstock'}
_STOCK_AND_SLIDES = _STOCK | {'google-slides'}

# Links each department doesn't need, by data-link name. A department not
# listed sees them all.
HIDDEN_LINKS = {
    'client_servicing': _STOCK,
    'project_owner': _STOCK,
    'finance': _STOCK_AND_SLIDES | {'digital-innovation'},
    'hr': _STOCK_AND_SLIDES,
    'production': _STOCK_AND_SLIDES,
    'logistics': _STOCK_AND_SLIDES,
}

# Management sees the company-wide view, whatever their department.
MANAGEMENT_HIDDEN = _STOCK


def show_link(link, user=None):
    """True if the sidebar should show `link` to `user` (default: the effective
    user, so admin's "view as" preview shows the emulated person's sidebar)."""
    actor = user if user is not None else effective_user()
    if getattr(actor, 'is_admin', False):
        return True
    if link in UNBUILT:
        return False
    if is_management(actor):
        return link not in MANAGEMENT_HIDDEN
    return link not in HIDDEN_LINKS.get(getattr(actor, 'department', None), ())
