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
    EXPIRING_SOON_DAYS, closed_on_time, days_owned, days_to_expiry,
    expiry_status, sla_days,
)
from app.modules.hse.lib.registers import BY_KEY
from app.modules.hse.lib.schedule import coverage


def expiry_registers():
    """Registers whose status is a function of a due date — the set
    compliance health is measured over."""
    return tuple(k for k, reg in BY_KEY.items() if reg.status_source == 'expiry')


def _expiring(entries):
    keys = set(expiry_registers())
    return [e for e in entries if e.register in keys and e.due_at is not None]


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
