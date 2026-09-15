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
from app.modules.hse.lib.vocab import OPEN_STATUSES
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
        'title': ((entry.data or {}).get('description')
                  or (getattr(entry, 'compliance_item', None) and entry.compliance_item.label)
                  or _label(entry)),
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
            'title': (getattr(entry, 'compliance_item', None) and entry.compliance_item.label) or _label(entry),
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


# Severity order, worst last, so the bars read as a ramp rather than a
# jumble. The tone names are the ones hse.css paints.
SEVERITY_BARS = (('Low', 'good'), ('Medium', 'warn'),
                 ('High', 'late'), ('Critical', 'bad'))


def severity_breakdown(entries, start, end):
    """Incidents by severity over the period, as bars.

    Counted across the whole Incidents group — an injury is an incident
    whether it was filed under Incidents, First aid or Lost time injury —
    and each entry is counted once, in the register it was actually filed
    in, so nothing is double counted.

    The bars are scaled against the largest bar, not the total: with four
    severities a share-of-total bar is always short and tells you nothing.
    """
    rows = [e for e in entries
            if BY_KEY.get(e.register) is not None
            and BY_KEY[e.register].group == INCIDENT_GROUP
            and e.entry_date is not None and start <= e.entry_date <= end]

    counts = {label: 0 for label, _ in SEVERITY_BARS}
    for entry in rows:
        if entry.severity in counts:
            counts[entry.severity] += 1

    top = max(counts.values()) if counts else 0
    bars = [{'label': label, 'tone': tone, 'count': counts[label],
             'percent': round(counts[label] * 100 / top) if top else 0}
            for label, tone in SEVERITY_BARS]

    resolved = sum(1 for e in rows if e.closed_at is not None)
    return {'bars': bars, 'total': len(rows), 'resolved': resolved,
            'unrated': len(rows) - sum(counts.values())}


def this_week(schedules, entries, start, end, today=None):
    """The six numbers the weekly HSC report is built from.

    They are counted here rather than typed by him: every column of that
    report is derivable from the registers, which is why it is a generated
    view and not a register of its own.
    """
    today = today or date.today()

    def filed(*groups):
        return [e for e in entries
                if BY_KEY.get(e.register) is not None
                and BY_KEY[e.register].group in groups
                and e.entry_date is not None and start <= e.entry_date <= end]

    incidents = filed(INCIDENT_GROUP)
    near = sum(1 for e in incidents
               if (e.data or {}).get('event_class') == 'Near miss')
    cov = done_vs_due(schedules, entries, start, end, today)

    return {
        'incidents': len(incidents) - near,
        'near_misses': near,
        'inspections_done': cov['done'],
        'inspections_due': cov['due'],
        'trainings': len(filed('training')),
        'opened': sum(1 for e in entries
                      if e.entry_date is not None and start <= e.entry_date <= end
                      and BY_KEY.get(e.register) is not None
                      and BY_KEY[e.register].status_source == 'stored'),
        'closed': sum(1 for e in entries
                      if e.closed_at is not None and start <= e.closed_at <= end),
    }
