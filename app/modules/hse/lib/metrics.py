"""
Shared HSE metric definitions, each defined once so the Overview, My
performance and the register pages always show the same numbers. Computed
from entries at read time; nothing is stored.
"""

import re
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from app.modules.hse.lib.computed import (
    EXPIRING_SOON_DAYS, closed_on_time, days_open, days_owned,
    days_to_expiry, expiry_status, sla_days,
)
from app.modules.hse.lib.registers import (
    BY_KEY, counts_as_done, money_fields, money_registers,
)
from app.modules.hse.lib.schedule import coverage


# Registers that count as training delivered. Training expenses are excluded.
TRAINING_REGISTERS = ('induction_training', 'toolbox_talk')


def expiry_registers():
    """Registers whose status comes from a due date; compliance health is
    measured over these."""
    return tuple(k for k, reg in BY_KEY.items() if reg.status_source == 'expiry')


def _filed_after(entry, other):
    """Later issue date wins; on the same date the higher id is the later
    filing."""
    if entry.entry_date != other.entry_date:
        return (entry.entry_date or date.min) > (other.entry_date or date.min)
    return (entry.id or 0) > (other.id or 0)


def _expiring(entries):
    """Expiry entries to measure: the latest entry per compliance item, plus
    every entry with no item set. Superseded renewals must be skipped or
    they read as lapsed and lower the score."""
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
    """Items valid today / items tracked, plus the `lapsed` and `expiring`
    entries. Read by the Overview tile and My performance."""
    today = today or date.today()
    items = _expiring(entries)
    if not items:
        # Nothing tracked: percent is None, not 0.
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
    """Items still valid but within EXPIRING_SOON_DAYS of expiry."""
    today = today or date.today()
    return sum(1 for e in _expiring(entries)
               if 0 <= (days_to_expiry(e, today) or -1) <= EXPIRING_SOON_DAYS)


def sla_pressure(entry, today=None):
    """Days past the SLA (negative = time left), or None when there is no
    SLA or it is closed. Uses days_owned, so time waiting on others is
    excluded."""
    allowed = sla_days(entry)
    if allowed is None or entry.closed_at is not None:
        return None
    owned = days_owned(entry, today)
    if owned is None:
        return None
    return owned - allowed


def closed_on_time_rate(entries, start, end, today=None):
    """Share of entries closed in the period that closed within their SLA.
    percent is None when none could be judged (not 0%)."""
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
    """Planned work done / due; delegates to schedule.coverage()."""
    return coverage(schedules, entries, start, end, today)


def average_days_to_close(entries, start, end):
    """Mean days from entry date to close, over entries closed in the
    period. Calendar days, including time waiting on others (the SLA rate
    is the one that excludes it)."""
    closed = [e for e in entries
              if e.closed_at is not None and start <= e.closed_at <= end]
    spans = [d for d in (days_open(e) for e in closed) if d is not None]
    if not spans:
        return {'days': None, 'closed': len(closed)}
    return {'days': round(sum(spans) / len(spans), 1), 'closed': len(closed)}


def near_miss_ratio(entries, start, end):
    """Near misses per incident, from the Incidents register only (so an
    injury also logged under First Aid is not counted twice). ratio is None
    when there are no incidents; `unclassified` counts entries with no
    event_class."""
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
    """Sessions and attendees across both training registers, with a
    per-type breakdown. A talk still scheduled or cancelled was not held."""
    rows = [e for e in entries
            if e.register in TRAINING_REGISTERS and counts_as_done(e)
            and e.entry_date is not None and start <= e.entry_date <= end]
    by_type = {}
    attendees = 0
    for entry in rows:
        data = entry.data or {}
        count = data.get('attendees') or 0
        attendees += count
        # Toolbox talks have no type field; the register label is the type.
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


# Stripped before parsing a stored amount: thousands commas, spaces, the unit.
_MONEY_NOISE = re.compile(r'[,\s]|aed', re.IGNORECASE)


def parse_money(value):
    """A stored amount as a Decimal, or None when blank, negative or not a
    number. Accepts numbers and text such as '1,250.50' or 'AED 300'."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        amount = Decimal(_MONEY_NOISE.sub('', str(value)))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def spend_of(entry):
    """One entry's spend: the sum of every money field its register declares."""
    reg = BY_KEY.get(entry.register)
    if reg is None:
        return Decimal(0)
    data = entry.data or {}
    amounts = (parse_money(data.get(fl.name)) for fl in money_fields(reg))
    return sum((a for a in amounts if a is not None), Decimal(0))


def _spent(entries, start=None, end=None):
    """Spend dated by entry_date within [start, end]; no bounds is all time."""
    if start is None:
        return sum((spend_of(e) for e in entries), Decimal(0))
    return sum((spend_of(e) for e in entries
                if e.entry_date is not None and start <= e.entry_date <= end),
               Decimal(0))


def spend_summary(entries, today=None):
    """Spend this calendar month, this calendar year and all time, by entry
    date. Whole periods, so a later-dated entry this month still counts."""
    today = today or date.today()
    last_day = monthrange(today.year, today.month)[1]
    return {
        'month': _spent(entries, today.replace(day=1), today.replace(day=last_day)),
        'year': _spent(entries, date(today.year, 1, 1), date(today.year, 12, 31)),
        'all_time': _spent(entries),
    }


def spend_by_month(entries, year):
    """Spend per calendar month of `year`, January first, plus the total."""
    months = [Decimal(0)] * 12
    for entry in entries:
        if entry.entry_date is not None and entry.entry_date.year == year:
            months[entry.entry_date.month - 1] += spend_of(entry)
    return {'year': year, 'months': months, 'total': sum(months, Decimal(0))}


def _share(amount, total):
    return round(amount * 100 / total) if total else 0


def spend_by_area(entries, start, end):
    """Spend per rail group over the period, each split by register. Every
    group and register with a money field is listed, even at zero; shares
    are of the period total, so a register's share is part of its group's."""
    areas = {}
    for reg in money_registers():
        area = areas.setdefault(reg.group, {'group': reg.group, 'amount': Decimal(0),
                                            'registers': {}})
        area['registers'][reg.key] = {'key': reg.key, 'label': reg.label,
                                      'amount': Decimal(0)}

    for entry in entries:
        if entry.entry_date is None or not start <= entry.entry_date <= end:
            continue
        reg = BY_KEY.get(entry.register)
        if reg is None or reg.group not in areas:
            continue
        amount = spend_of(entry)
        areas[reg.group]['amount'] += amount
        areas[reg.group]['registers'][reg.key]['amount'] += amount

    total = sum((a['amount'] for a in areas.values()), Decimal(0))
    out = []
    for area in areas.values():
        registers = list(area['registers'].values())
        for row in registers:
            row['share'] = _share(row['amount'], total)
        out.append(dict(area, share=_share(area['amount'], total), registers=registers))
    return {'total': total, 'areas': out}
