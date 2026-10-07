"""The cards of the admin system pages. Each card is a part: the page loads and
refreshes it from /dashboard/api/admin/<page>/<part>. A part whose data is
missing or half-written reads as "No data", never an error. One module per page."""
from datetime import datetime

from app.modules.dashboard.lib.admin_pages import (database, errors, jobs, overview, performance, system,
                                                   uptime, usage)
from app.modules.dashboard.lib.admin_pages.common import badge, when  # noqa: F401  re-exported
from app.modules.system.services.snapshot import read_snapshot

_PAGES = {'overview': overview, 'system': system, 'database': database, 'performance': performance,
          'usage': usage, 'errors': errors, 'uptime': uptime, 'jobs': jobs}
PARTS = {key: page.PARTS for key, page in _PAGES.items()}
# Pages drawn by the shared cards template: their rows of parts.
LAYOUTS = {key: page.LAYOUT for key, page in _PAGES.items() if hasattr(page, 'LAYOUT')}
HELP_KEYS = {key: getattr(page, 'HELP', 'dashboard.admin') for key, page in _PAGES.items()}


def part_context(page, part, snapshot=None, now=None):
    """What one part's template reads. Half-written data (a snapshot from an
    older collector, a field it lacked) gives {'missing': True}, shown as No data."""
    snapshot = read_snapshot() if snapshot is None else snapshot
    try:
        return PARTS[page][part](snapshot, now or datetime.utcnow())
    except (KeyError, TypeError, ValueError, AttributeError):
        return {'missing': True}
