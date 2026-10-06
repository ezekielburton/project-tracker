"""The frame every dashboard rail page shares: the rail's items, the check that
a page is on the person's rail, and the context the shell template reads."""
from datetime import datetime
from functools import wraps

from flask import abort, url_for

from app.modules.core.shared.lib import org
from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.dashboard.lib.project_loader import load_new_briefs
from app.modules.dashboard.lib.rail_counts import rail_counts
from app.modules.dashboard.lib.rails import PAGES, rail_for


def rail_items(user):
    """Items for the shared module_rail: `user`'s rail with badge counts; a page with no route shows Soon."""
    counts = rail_counts(user)
    items = []
    for key in rail_for(user).pages:
        page = PAGES[key]
        item = {'key': key, 'label': page.label, 'icon': page.icon,
                'url': url_for(page.endpoint) if page.endpoint else None}
        if page.endpoint is None:
            item['soon'] = True
        if counts.get(key):
            item['count'] = counts[key]
        items.append(item)
    return items


def on_rail(key):
    """403 unless page `key` is on the effective user's rail, so a typed URL opens
    only what the rail shows. Admin opens any page."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = effective_user()
            # Branch check, not can(): this asks which rail, not whether allowed.
            if not org.is_admin(user) and key not in rail_for(user).pages:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def _age_label(created_at, today):
    if created_at is None:
        return ''
    days = (today - created_at.date()).days
    return 'Today' if days <= 0 else f'{days}d'


def brief_rows(projects, today=None):
    """New briefs as display rows: name, client, CS lead, age and the link that opens the project."""
    today = today or datetime.utcnow().date()
    return [{
        'name': p.name,
        'client': p.client or '',
        'cs_lead': p.cs_lead.name if p.cs_lead else '',
        'age': _age_label(p.created_at, today),
        'url': url_for('project_list.index', project=p.id),
    } for p in projects]


def page_context(active):
    """What the shell template reads for page `active`; New briefs only on the rail's landing page."""
    user = effective_user()
    landing = active == rail_for(user).landing
    return {
        'rail_items': rail_items(user),
        'rail_active': active,
        'page_title': PAGES[active].label,
        'new_briefs': brief_rows(load_new_briefs()) if landing else None,
    }
