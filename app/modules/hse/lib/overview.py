"""
The Overview's view model: the module's landing page, led by what needs
action today. Shared metrics come from lib/metrics.py so this page and My
performance agree; nothing is stored.
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

# Rows per panel before it shows "and N more".
PANEL_LIMIT = 6

# The rail group whose open items are "incidents" for the tile.
INCIDENT_GROUP = 'incidents'


def _label(entry):
    reg = BY_KEY.get(entry.register)
    return reg.label if reg else entry.register


# Longest a free-text title runs before it is cut.
TITLE_MAX = 60

# JSONB fields naming what kind of thing happened, tried in order.
_KIND_FIELDS = ('document_type', 'service_type', 'maintenance_type',
                'inspection_type', 'injury_type', 'ppe_type', 'body_part',
                'incident_type', 'issue_type')


def _short(text):
    text = ' '.join(str(text).split())
    return text if len(text) <= TITLE_MAX else text[:TITLE_MAX - 1].rstrip() + '…'


def entry_title(entry):
    """A short human title for an entry: the certificate, asset + kind,
    item, person + kind, kind + location, or description, whichever comes
    first. Falls back to the register's name."""
    data = entry.data or {}
    kind = next((data[k] for k in _KIND_FIELDS if data.get(k)), None)

    def with_kind(name):
        return f'{name} — {kind}' if kind else name

    item = getattr(entry, 'compliance_item', None)
    if item is not None:
        return item.label
    asset = getattr(entry, 'asset', None)
    if asset is not None:
        return with_kind(asset.label)
    if data.get('item'):
        return _short(data['item'])
    subject = getattr(entry, 'subject', None)
    if subject is not None:
        return with_kind(subject.name)
    location = getattr(entry, 'location', None)
    if kind:
        return f'{kind} — {location.label}' if location is not None else kind
    for key in ('description', 'issues_found', 'topic'):
        if data.get(key):
            return _short(data[key])
    if location is not None:
        return location.label
    return _label(entry)


def _open(entries):
    """Open entries in stored-status registers. Logs are never open; expiry
    registers are covered by compliance health."""
    out = []
    for entry in entries:
        reg = BY_KEY.get(entry.register)
        if reg is None or reg.status_source != 'stored':
            continue
        if entry.closed_at is None and entry.status in OPEN_STATUSES:
            out.append(entry)
    return out


def open_incident_count(entries):
    """Open entries across the whole Incidents rail group, not only the
    Incidents register."""
    # _open has already dropped anything whose register is unknown.
    return sum(1 for e in _open(entries)
               if BY_KEY[e.register].group == INCIDENT_GROUP)


def needs_you_now(entries, today=None, limit=PANEL_LIMIT):
    """Open work, most overdue against its SLA first. Entries waiting on
    someone else are left out (see waiting_on_others)."""
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
        'title': entry_title(entry),
        'severity': entry.severity,
        'days_open': days_open(entry, today),
        'over_sla': pressure if pressure > 0 else 0,
        'status': effective_status(entry, BY_KEY[entry.register], today),
    } for pressure, entry in scored[:limit]]
    return {'rows': rows, 'total': len(scored), 'more': max(0, len(scored) - limit)}


def waiting_on_others(entries, today=None, limit=PANEL_LIMIT):
    """Open work waiting on someone else, longest-waiting first."""
    today = today or date.today()
    parked = [e for e in _open(entries) if e.waiting_on_id is not None]
    parked.sort(key=lambda e: e.waiting_since or e.entry_date or today)
    rows = [{
        'entry': entry,
        'ref': entry.ref,
        'register_label': _label(entry),
        'title': entry_title(entry),
        'person': entry.waiting_on.name if entry.waiting_on else 'Someone',
        'days': days_waiting(entry, today),
    } for entry in parked[:limit]]
    return {'rows': rows, 'total': len(parked), 'more': max(0, len(parked) - limit)}


def expiring_panel(health, today=None, limit=PANEL_LIMIT):
    """Lapsed compliance items first, then those expiring soon."""
    today = today or date.today()
    rows = []
    for entry in health['lapsed'] + health['expiring']:
        remaining = days_to_expiry(entry, today)
        rows.append({
            'entry': entry,
            'ref': entry.ref,
            'register_label': _label(entry),
            'title': entry_title(entry),
            'due_at': entry.due_at,
            'days': remaining,
            'lapsed': remaining is not None and remaining < 0,
        })
    total = len(rows)
    return {'rows': rows[:limit], 'total': total, 'more': max(0, total - limit)}


def tiles(schedules, entries, month_start, month_end, today=None):
    """The tile counts across the top, plus the compliance health dict
    (from lib/metrics) for the expiring panel."""
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


# Severity order, worst last. Tone names must match the classes in hse.css.
SEVERITY_BARS = (('Low', 'good'), ('Medium', 'warn'),
                 ('High', 'late'), ('Critical', 'bad'))


def severity_breakdown(entries, start, end):
    """Incidents-group entries by severity over the period, as bars. Each
    entry counts once; bar length is relative to the largest bar, not the
    total."""
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
    """The weekly HSC report figures, derived from the registers for the
    given period."""
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
