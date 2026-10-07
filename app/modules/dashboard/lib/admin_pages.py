"""The cards of the admin Overview and System pages. Each card is a part: the
page loads and refreshes it from /dashboard/api/admin/<page>/<part>. A part
whose data is missing or half-written reads as "No data", never an error."""
from datetime import datetime, timedelta

from flask import url_for

from app.modules.dashboard.lib import admin_charts
from app.modules.dashboard.lib.rails import PAGES
from app.modules.system.lib import fmt
from app.modules.system.services import health
from app.modules.system.services.snapshot import read_snapshot

CERT_WARN_DAYS, CERT_BAD_DAYS = 30, 7
TEMP_WARN_C, TEMP_BAD_C = 75, 85


def _link(page_key):
    page = PAGES[page_key]
    return {'label': page.label, 'url': url_for(page.endpoint)}


def when(moment, now):
    """'in 2 min', 'today 23:00', 'Sun 04:00' for a naive-UTC moment."""
    minutes = (moment - now).total_seconds() / 60
    if minutes < 60:
        return f'in {max(int(minutes), 0)} min'
    local, today = fmt.local(moment), fmt.local(now)
    if local.date() == today.date():
        return f"today {local:%H:%M}"
    if local.date() == today.date() + timedelta(days=1):
        return f"tomorrow {local:%H:%M}"
    return f"{local:%a %H:%M}"


# ── Overview ─────────────────────────────────────────────────────────────

def _strip(snapshot, now):
    return {'tiles': health.status_strip(snapshot, now)}


def _attention(snapshot, now):
    items = health.needs_attention(snapshot, now)
    for item in items:
        item['link'] = _link(item['page'])
    return {'items': items, 'headline': health.headline(snapshot, items, now)}


def _today(snapshot, now):
    numbers = health.today(now)
    weeks = numbers['weeks']
    labels = [f"{week['start'].day} {week['start']:%b}" for week in (weeks[0], weeks[len(weeks) // 2], weeks[-1])]
    return dict(numbers, chart=admin_charts.bars([week['actions'] for week in weeks]), labels=labels)


def _jobs(snapshot, now):
    upcoming = health.next_jobs(snapshot)
    for job in upcoming:
        job['when'] = when(job['next'], now)
    return {'jobs': upcoming, 'jobs_url': url_for('projects.admin_jobs')}


# ── System ───────────────────────────────────────────────────────────────

def _state(value, warn, bad, high_is_bad=True):
    if value is None:
        return health.GREY
    if high_is_bad:
        return health.RED if value >= bad else health.AMBER if value >= warn else health.GREEN
    return health.RED if value <= bad else health.AMBER if value <= warn else health.GREEN


def _tiles(snapshot, now):
    tiles = health.host_tiles(snapshot)
    if tiles and tiles['temp_c'] is not None:
        tiles['temp_state'] = _state(tiles['temp_c'], TEMP_WARN_C, TEMP_BAD_C)
    return {'tiles': tiles}


def _storage(snapshot, now):
    return {'rows': health.storage(snapshot)}


def _network(snapshot, now):
    series = health.network(now)
    start = now - timedelta(hours=24)
    if not any(series.values()):
        return {'chart': None}
    return {'chart': admin_charts.lines(series, start, now),
            'ticks': admin_charts.time_ticks(start, now, fmt.local)}


def _updates(snapshot, now):
    updates = health.updates(snapshot, now)
    if updates:
        for cert in updates['certs']:
            cert['state'] = _state(cert['days_left'], CERT_WARN_DAYS, CERT_BAD_DAYS, high_is_bad=False)
    return {'updates': updates}


def _application(snapshot, now):
    return {'app': health.application(snapshot, now)}


PARTS = {
    'overview': {'strip': _strip, 'attention': _attention, 'today': _today, 'jobs': _jobs},
    'system': {'tiles': _tiles, 'storage': _storage, 'network': _network,
               'updates': _updates, 'application': _application},
}


def part_context(page, part, snapshot=None, now=None):
    """What one part's template reads. Half-written data (a snapshot from an
    older collector, a field it lacked) gives {'missing': True}, shown as No data."""
    snapshot = read_snapshot() if snapshot is None else snapshot
    try:
        return PARTS[page][part](snapshot, now or datetime.utcnow())
    except (KeyError, TypeError, ValueError, AttributeError):
        return {'missing': True}
