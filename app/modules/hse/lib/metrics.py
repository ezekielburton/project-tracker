"""
The numbers this module reports, each defined exactly once.

Every metric here is read by more than one page. The Overview shows
compliance health as a tile; My performance shows it as a section; the
calendar header shows coverage. Two pages showing different numbers for
the same word is the trust problem this module exists to fix, so the
definition lives here and the pages read it.

Nothing is stored. Every figure is computed from entries at read time.
"""

from datetime import date

from app.modules.hse.lib.computed import (
    EXPIRING_SOON_DAYS, closed_on_time, days_open, days_owned,
    days_to_expiry, expiry_status, sla_days,
)
from app.modules.hse.lib.registers import BY_KEY
from app.modules.hse.lib.schedule import coverage


# Delivery, not spend. Training expenses are money and are counted on the
# cost line, never as a session the officer ran.
TRAINING_REGISTERS = ('induction_training', 'toolbox_talk')


def expiry_registers():
    """Registers whose status is a function of a due date — the set
    compliance health is measured over."""
    return tuple(k for k, reg in BY_KEY.items() if reg.status_source == 'expiry')


def _filed_after(entry, other):
    """Later issue date wins; on the same date the higher id is the later
    filing."""
    if entry.entry_date != other.entry_date:
        return (entry.entry_date or date.min) > (other.entry_date or date.min)
    return (entry.id or 0) > (other.id or 0)


def _expiring(entries):
    """The items compliance health is measured over — one row per
    certificate, not one per renewal.

    Renewing files a new entry and leaves the old one in the register.
    Counting both makes renewing *lower* the score: the superseded row
    expires on its old date and reads as lapsed while its replacement reads
    as valid. The certificate is the thing being tracked, so only its most
    recent entry counts.

    An entry with no certificate set is counted on its own — it has no
    history to supersede.
    """
    keys = set(expiry_registers())
    rows = [e for e in entries if e.register in keys and e.due_at is not None]

    latest, loose = {}, []
    for entry in rows:
        item_id = getattr(entry, 'compliance_item_id', None)
        if item_id is None:
            loose.append(entry)
            continue
        current = latest.get(item_id)
        if current is None or _filed_after(entry, current):
            latest[item_id] = entry
    return list(latest.values()) + loose


def compliance_health(entries, today=None):
    """Items valid today, divided by items tracked.

    The one definition. The Overview's tile and My performance both read
    this; neither recomputes it.

    `lapsed` names what expired rather than hiding it. A page that only
    flatters is worth nothing in the room, and the officer needs the list
    more than the manager needs the percentage.
    """
    today = today or date.today()
    items = _expiring(entries)
    if not items:
        # Nothing tracked is not the same as nothing valid.
        return {'percent': None, 'valid': 0, 'total': 0, 'lapsed': [], 'expiring': []}

    valid, lapsed, expiring = 0, [], []
    for entry in items:
        status = expiry_status(entry, today)
        if status == 'Expired':
            lapsed.append(entry)
        else:
            valid += 1
            if status == 'Expiring soon':
                expiring.append(entry)

    lapsed.sort(key=lambda e: e.due_at)
    expiring.sort(key=lambda e: e.due_at)
    return {
        'percent': round(valid * 100 / len(items)),
        'valid': valid,
        'total': len(items),
        'lapsed': lapsed,
        'expiring': expiring,
    }


def expiring_soon_count(entries, today=None):
    """Items still valid but inside the workbook's own 30-day window."""
    today = today or date.today()
    return sum(1 for e in _expiring(entries)
               if 0 <= (days_to_expiry(e, today) or -1) <= EXPIRING_SOON_DAYS)


def sla_pressure(entry, today=None):
    """Days past the SLA for this entry, or None when it has no clock.

    Negative means time left. Time parked with someone else is already
    excluded by days_owned, so an action waiting on the production manager
    does not climb this list.
    """
    allowed = sla_days(entry)
    if allowed is None or entry.closed_at is not None:
        return None
    owned = days_owned(entry, today)
    if owned is None:
        return None
    return owned - allowed


def closed_on_time_rate(entries, start, end, today=None):
    """Of entries closed in the period, the share closed inside their SLA.

    None when nothing closed — a period with no closures has no rate, and
    showing 0% would read as failure rather than quiet.
    """
    closed = [e for e in entries
              if e.closed_at is not None and start <= e.closed_at <= end]
    judged = [e for e in closed if closed_on_time(e, today) is not None]
    if not judged:
        return {'percent': None, 'closed': len(closed), 'judged': 0}
    on_time = sum(1 for e in judged if closed_on_time(e, today))
    return {
        'percent': round(on_time * 100 / len(judged)),
        'closed': len(closed),
        'judged': len(judged),
    }


def done_vs_due(schedules, entries, start, end, today=None):
    """Planned work done over planned work due — the calendar's coverage,
    read rather than recomputed."""
    return coverage(schedules, entries, start, end, today)


def average_days_to_close(entries, start, end):
    """Mean days from entry date to closing date, over entries closed in
    the period.

    Calendar days, not owned days: this answers how long the person who
    raised it actually waited, and they waited through the parked time
    too. closed_on_time_rate is the one that excludes it, because that is
    the one judging him.
    """
    closed = [e for e in entries
              if e.closed_at is not None and start <= e.closed_at <= end]
    spans = [d for d in (days_open(e) for e in closed) if d is not None]
    if not spans:
        return {'days': None, 'closed': len(closed)}
    return {'days': round(sum(spans) / len(spans), 1), 'closed': len(closed)}


def near_miss_ratio(entries, start, end):
    """Near misses raised for every incident that happened.

    Counted from the Incidents register alone: an injury logged there and
    again under First Aid would otherwise be two incidents.

    None when nothing was recorded — dividing by nothing is not a perfect
    score. `unclassified` is entries filed before the field existed, and
    the page shows it rather than folding them into either side.
    """
    rows = [e for e in entries
            if e.register == 'incidents'
            and e.entry_date is not None and start <= e.entry_date <= end]
    classes = [(e.data or {}).get('event_class') for e in rows]
    near = sum(1 for c in classes if c == 'Near miss')
    incidents = sum(1 for c in classes if c == 'Incident')
    return {
        'ratio': round(near / incidents, 1) if incidents else None,
        'near_misses': near,
        'incidents': incidents,
        'unclassified': sum(1 for c in classes if c is None),
    }


def training_delivered(entries, start, end):
    """Sessions run and people in the room, over both training registers.

    An induction and a toolbox talk are both delivery — he ran the room
    either way — so they are one number, broken out by type underneath.
    """
    rows = [e for e in entries
            if e.register in TRAINING_REGISTERS
            and e.entry_date is not None and start <= e.entry_date <= end]
    by_type = {}
    attendees = 0
    for entry in rows:
        data = entry.data or {}
        count = data.get('attendees') or 0
        attendees += count
        # A toolbox talk has no type field — the register is the type.
        label = data.get('training_type') or BY_KEY[entry.register].label
        bucket = by_type.setdefault(label, {'label': label, 'sessions': 0,
                                            'attendees': 0})
        bucket['sessions'] += 1
        bucket['attendees'] += count
    return {
        'sessions': len(rows),
        'attendees': attendees,
        'by_type': sorted(by_type.values(),
                          key=lambda b: (-b['attendees'], b['label'])),
    }
