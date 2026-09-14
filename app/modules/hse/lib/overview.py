"""
The Overview's view model — what the officer sees when he opens the module.

The page answers one question in its first screen: what needs him today.
Everything else is context for that. Nothing here is stored and nothing
here defines a metric — the shared definitions live in lib/metrics.py so
this page and My performance can never disagree.
"""

from datetime import date

from app.modules.hse.lib.computed import (
    days_open, days_to_expiry, days_waiting, effective_status,
)
from app.modules.hse.lib.metrics import (
    compliance_health, done_vs_due, expiring_soon_count, sla_pressure,
)
from app.modules.hse.lib.query import OPEN_STATUSES
from app.modules.hse.lib.registers import BY_KEY

# How many rows each panel shows before it starts saying "and N more". The
# Overview is a place to start work, not a second register.
PANEL_LIMIT = 6

# The rail group whose open items are "incidents" for the tile.
INCIDENT_GROUP = 'incidents'


def _label(entry):
    reg = BY_KEY.get(entry.register)
    return reg.label if reg else entry.register


def _open(entries):
    """Entries still needing someone. A log has no status and is never
    open; an expiry register's status is computed, and its overdue items
    are counted by compliance health instead."""
    out = []
    for entry in entries:
        reg = BY_KEY.get(entry.register)
        if reg is None or reg.status_source != 'stored':
            continue
        if entry.closed_at is None and entry.status in OPEN_STATUSES:
            out.append(entry)
    return out


def open_incident_count(entries):
    """Open work in the Incidents group — incidents, first aid, PPE
    non-conformity and lost time injuries, not just the one register."""
    # _open has already dropped anything whose register is unknown.
    return sum(1 for e in _open(entries)
               if BY_KEY[e.register].group == INCIDENT_GROUP)


def needs_you_now(entries, today=None, limit=PANEL_LIMIT):
    """Open work ordered by how far past its SLA it is.

    Time parked with someone else is already out of the clock, so an action
    he has chased and is waiting on does not crowd out the work he can
    actually do. Those appear in waiting_on_others instead.
    """
    today = today or date.today()
    scored = []
    for entry in _open(entries):
        if entry.waiting_on_id is not None:
            continue
        pressure = sla_pressure(entry, today)
        scored.append((pressure if pressure is not None else -999, entry))

    scored.sort(key=lambda pair: (-pair[0], pair[1].entry_date or today))
    rows = [{
        'entry': entry,
        'register_label': _label(entry),
        'ref': entry.ref,
        'title': (entry.data or {}).get('description')
                 or (entry.data or {}).get('item')
                 or _label(entry),
        'severity': entry.severity,
        'days_open': days_open(entry, today),
        'over_sla': pressure if pressure > 0 else 0,
        'status': effective_status(entry, BY_KEY[entry.register], today),
    } for pressure, entry in scored[:limit]]
    return {'rows': rows, 'total': len(scored), 'more': max(0, len(scored) - limit)}


def waiting_on_others(entries, today=None, limit=PANEL_LIMIT):
    """Work parked with someone else.

    It sits in its own panel on purpose. The performance page refuses to
    measure what the officer does not control, and the Overview should not
    make him feel he is behind on something he has already chased.
    """
    today = today or date.today()
    parked = [e for e in _open(entries) if e.waiting_on_id is not None]
    parked.sort(key=lambda e: e.waiting_since or e.entry_date or today)
    rows = [{
        'entry': entry,
        'ref': entry.ref,
        'register_label': _label(entry),
        'title': (entry.data or {}).get('description') or _label(entry),
        'person': entry.waiting_on.name if entry.waiting_on else 'Someone',
        'days': days_waiting(entry, today),
    } for entry in parked[:limit]]
    return {'rows': rows, 'total': len(parked), 'more': max(0, len(parked) - limit)}


def expiring_panel(health, today=None, limit=PANEL_LIMIT):
    """What has lapsed, then what is about to. Lapsed first because it is
    already a problem, and naming it is the point."""
    today = today or date.today()
    rows = []
    for entry in health['lapsed'] + health['expiring']:
        remaining = days_to_expiry(entry, today)
        rows.append({
            'entry': entry,
            'ref': entry.ref,
            'register_label': _label(entry),
            'title': (entry.data or {}).get('item') or _label(entry),
            'due_at': entry.due_at,
            'days': remaining,
            'lapsed': remaining is not None and remaining < 0,
        })
    total = len(rows)
    return {'rows': rows[:limit], 'total': total, 'more': max(0, total - limit)}


def tiles(schedules, entries, month_start, month_end, today=None):
    """The five counts across the top.

    Compliance health is read from lib/metrics, not computed here, so the
    tile and the performance page cannot drift apart.
    """
    today = today or date.today()
    health = compliance_health(entries, today)
    cov = done_vs_due(schedules, entries, month_start, month_end, today)
    needs = needs_you_now(entries, today)

    return {
        'needs_you_now': needs['total'],
        'open_incidents': open_incident_count(entries),
        'done': cov['done'],
        'due': cov['due'],
        'expiring_soon': expiring_soon_count(entries, today),
        'health_percent': health['percent'],
        'health_valid': health['valid'],
        'health_total': health['total'],
    }, health
