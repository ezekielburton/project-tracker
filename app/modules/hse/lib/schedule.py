"""
Recurring schedules expanded into occurrences, computed at read time.

Occurrences are never stored. Completed work is an ordinary HseEntry with
schedule_id and occurrence_date set; that pair is what counts it here.
Nothing in this module writes.

Dates anchor to the schedule's starts_on, not the requested window, so a
schedule yields the same dates for any window size.
"""

from calendar import monthrange
from datetime import date, timedelta

from app.modules.hse.lib.registers import counts_as_done


FREQUENCIES = ('daily', 'weekly', 'monthly', 'quarterly', 'annual')

# Months per step, multiplied by the schedule's interval (six-monthly =
# 'monthly' x 6 or 'quarterly' x 2).
_MONTH_STEP = {'monthly': 1, 'quarterly': 3, 'annual': 12}

# Runaway guard for malformed data; no real schedule gets near it.
_MAX_OCCURRENCES = 2000


def _interval(schedule):
    """The schedule's interval; missing, invalid or below 1 becomes 1."""
    try:
        n = int(schedule.interval or 1)
    except (TypeError, ValueError):
        return 1
    return n if n >= 1 else 1


def _clamp(year, month, day):
    """A date with the day clamped to the month's length (31st -> 30th)."""
    return date(year, month, min(day, monthrange(year, month)[1]))


def _month_index(d):
    return d.year * 12 + (d.month - 1)


def _from_index(index, day):
    return _clamp(index // 12, index % 12 + 1, day)


def add_months(day, months):
    """`day` moved by whole months, clamped to the target month's length."""
    return _from_index(_month_index(day) + months, day.day)


def _day_dates(schedule, lo, hi, step_days):
    """Dates for the fixed-length frequencies (daily, weekly)."""
    anchor = schedule.starts_on
    if schedule.frequency == 'weekly':
        target = schedule.weekday
        if target is None:
            target = anchor.weekday()
        anchor = anchor + timedelta(days=(target - anchor.weekday()) % 7)

    cur = anchor
    if lo > anchor:
        # Jump to the window without walking the history.
        cur = anchor + timedelta(days=((lo - anchor).days // step_days) * step_days)

    out = []
    while cur <= hi and len(out) < _MAX_OCCURRENCES:
        if cur >= lo:
            out.append(cur)
        cur += timedelta(days=step_days)
    return out


def _month_dates(schedule, lo, hi, step_months):
    """Dates for the month-based frequencies, on the schedule's day of month
    (clamped in short months)."""
    anchor = schedule.starts_on
    day = schedule.day_of_month or anchor.day

    index = _month_index(anchor)
    if _from_index(index, day) < anchor:
        # The day has already passed in the starting month.
        index += step_months

    if lo > _from_index(index, day):
        # Floor the jump so clamping can never skip the first date in view.
        steps = max(0, (_month_index(lo) - index) // step_months)
        index += steps * step_months

    out = []
    while len(out) < _MAX_OCCURRENCES:
        d = _from_index(index, day)
        if d > hi:
            break
        if d >= lo and d >= anchor:
            out.append(d)
        index += step_months
    return out


def occurrence_dates(schedule, window_start, window_end):
    """Every date this schedule falls due inside the window, inclusive."""
    if not getattr(schedule, 'active', True) or schedule.starts_on is None:
        return []

    lo = max(window_start, schedule.starts_on)
    hi = window_end
    if schedule.ends_on is not None:
        hi = min(hi, schedule.ends_on)
    if lo > hi:
        return []

    n = _interval(schedule)
    if schedule.frequency == 'daily':
        return _day_dates(schedule, lo, hi, n)
    if schedule.frequency == 'weekly':
        return _day_dates(schedule, lo, hi, n * 7)

    step = _MONTH_STEP.get(schedule.frequency)
    if step is None:
        return []  # unknown frequency: never due
    return _month_dates(schedule, lo, hi, step * n)


def schedule_targets(schedule):
    """What one occurrence covers: each active asset, or [None] for a
    schedule with no assets. If every asset is retired, returns [] (due
    for nothing, not a general obligation)."""
    declared = list(schedule.assets or [])
    if not declared:
        return [None]
    return [a for a in declared if getattr(a, 'active', True)]


def _entry_index(entries):
    """Entries keyed by (schedule_id, occurrence_date). Entries missing
    either are unplanned, and entries not yet done (a talk still scheduled)
    tick nothing off; both are left out."""
    index = {}
    for e in entries:
        if e.schedule_id is None or e.occurrence_date is None:
            continue
        if not counts_as_done(e):
            continue
        index.setdefault((e.schedule_id, e.occurrence_date), []).append(e)
    return index


def occurrences(schedules, entries, window_start, window_end, today=None):
    """Occurrences in the window, one per schedule per date, each with its
    per-asset items. Matching uses occurrence_date, not entry_date, so late
    work ticks off the original day."""
    today = today or date.today()
    index = _entry_index(entries)

    out = []
    for schedule in schedules:
        targets = schedule_targets(schedule)
        if not targets:
            continue
        target_ids = {(t.id if t else None) for t in targets}

        for day in occurrence_dates(schedule, window_start, window_end):
            filed = index.get((schedule.id, day), [])

            items = []
            for target in targets:
                want = target.id if target else None
                match = next((e for e in filed if e.asset_id == want), None)
                items.append({'asset': target, 'entry': match,
                              'done': match is not None})

            # Keep work filed against assets that have since been retired.
            for e in filed:
                if e.asset_id not in target_ids:
                    items.append({'asset': e.asset, 'entry': e, 'done': True})

            due = len(targets)
            done = sum(1 for i in items if i['done'])
            if done >= due:
                state = 'done'
            elif day < today:
                state = 'overdue'
            else:
                state = 'planned'

            out.append({
                'schedule': schedule,
                'schedule_id': schedule.id,
                'register': schedule.register,
                'label': schedule.label,
                'date': day,
                'items': items,
                'due': due,
                'done': done,
                'state': state,
            })

    out.sort(key=lambda o: (o['date'], o['label'] or ''))
    return out


def coverage(schedules, entries, window_start, window_end, today=None):
    """Done / due over the window, counted per asset. The single source for
    the calendar header and the performance page. Due counts only
    occurrences on or before today."""
    today = today or date.today()
    due = done = 0
    for o in occurrences(schedules, entries, window_start, window_end, today):
        if o['date'] > today:
            continue
        due += o['due']
        done += min(o['done'], o['due'])
    return {
        'due': due,
        'done': done,
        'outstanding': due - done,
        # None when nothing was due; that is not a 0% score.
        'percent': round(done * 100 / due) if due else None,
    }


def falls_due_on(schedule, day):
    """True when this schedule falls due on that date. The write path checks
    this before linking an entry to an occurrence, so a forged request
    cannot tick off unplanned work."""
    return day in occurrence_dates(schedule, day, day)


def next_due(schedule, today=None, horizon_days=400):
    """The next date this schedule falls due, for the Schedule page. None
    when it has ended or nothing falls inside the horizon."""
    today = today or date.today()
    dates = occurrence_dates(schedule, today, today + timedelta(days=horizon_days))
    return dates[0] if dates else None
