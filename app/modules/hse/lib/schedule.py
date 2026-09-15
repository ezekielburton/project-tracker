"""
Recurring obligations turned into occurrences, computed at read time.

An occurrence is not a row and never becomes one. The only thing a
completed inspection writes is an ordinary HseEntry carrying schedule_id
and occurrence_date, which is what makes it count here. If anything in
this module ever writes, something has gone wrong.

Dates are anchored to the schedule's own starts_on, never to the window
being asked for, so a schedule yields the same dates whether the page is
rendering one week or a whole year.
"""

from calendar import monthrange
from datetime import date, timedelta


FREQUENCIES = ('daily', 'weekly', 'monthly', 'quarterly', 'annual')

# Months between occurrences, before the schedule's own interval. A
# six-monthly vehicle service is frequency='monthly', interval=6 — or
# 'quarterly' with interval=2; both land on the same dates.
_MONTH_STEP = {'monthly': 1, 'quarterly': 3, 'annual': 12}

# A guard, not a limit anyone should reach: it stops a malformed interval
# spinning rather than capping any real schedule.
_MAX_OCCURRENCES = 2000


def _interval(schedule):
    """Intervals below 1 would never advance. Treated as 1."""
    try:
        n = int(schedule.interval or 1)
    except (TypeError, ValueError):
        return 1
    return n if n >= 1 else 1


def _clamp(year, month, day):
    """The 31st of a 30-day month is that month's last day, not a skip."""
    return date(year, month, min(day, monthrange(year, month)[1]))


def _month_index(d):
    return d.year * 12 + (d.month - 1)


def _from_index(index, day):
    return _clamp(index // 12, index % 12 + 1, day)


def _day_dates(schedule, lo, hi, step_days):
    """Dates for the fixed-length frequencies — daily and weekly."""
    anchor = schedule.starts_on
    if schedule.frequency == 'weekly':
        target = schedule.weekday
        if target is None:
            target = anchor.weekday()
        anchor = anchor + timedelta(days=(target - anchor.weekday()) % 7)

    cur = anchor
    if lo > anchor:
        # Jump straight to the window instead of walking years of history.
        cur = anchor + timedelta(days=((lo - anchor).days // step_days) * step_days)

    out = []
    while cur <= hi and len(out) < _MAX_OCCURRENCES:
        if cur >= lo:
            out.append(cur)
        cur += timedelta(days=step_days)
    return out


def _month_dates(schedule, lo, hi, step_months):
    """Dates for the month-based frequencies. The day of the month is the
    schedule's own, clamped to months that are too short for it."""
    anchor = schedule.starts_on
    day = schedule.day_of_month or anchor.day

    index = _month_index(anchor)
    if _from_index(index, day) < anchor:
        # The chosen day has already gone in the starting month.
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
        return []  # an unknown frequency is due never, not every day
    return _month_dates(schedule, lo, hi, step * n)


def schedule_targets(schedule):
    """What one occurrence covers. A schedule with assets is due once per
    asset — six vehicles is six inspections. One without assets, like a
    tool box talk, is due once.

    A schedule whose assets have all been retired is due for nothing: it
    must not quietly turn into a general obligation.
    """
    declared = list(schedule.assets or [])
    if not declared:
        return [None]
    return [a for a in declared if getattr(a, 'active', True)]


def _entry_index(entries):
    """Entries filed against a planned occurrence, keyed by schedule and
    occurrence date. An entry without both is unplanned work and belongs
    to no occurrence."""
    index = {}
    for e in entries:
        if e.schedule_id is None or e.occurrence_date is None:
            continue
        index.setdefault((e.schedule_id, e.occurrence_date), []).append(e)
    return index


def occurrences(schedules, entries, window_start, window_end, today=None):
    """Occurrences in the window, one per schedule per date, each carrying
    its per-asset items. Nothing here is stored.

    An entry's own entry_date is not consulted: logging Monday's overdue
    inspection on Wednesday ticks off Monday, and the lateness stays
    visible rather than being back-dated away.
    """
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

            # Work filed against an asset since retired still happened. It
            # stays visible rather than vanishing from the day it was done.
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
    """Done divided by due over the window — the number the inspection
    tile and the performance page have both been missing a denominator
    for. Defined here once so the two pages can never disagree.

    Due counts only occurrences on or before today: a job scheduled for
    Friday is not missed on Wednesday, and counting it would make every
    month read badly until its last day.

    Counted per asset, so six vehicles missed reads six, not one.
    """
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
        # None, not 0 — nothing was due, which is not the same as failing.
        'percent': round(done * 100 / due) if due else None,
    }


def falls_due_on(schedule, day):
    """True when this schedule genuinely falls due on that date.

    The write path checks this before stamping an entry with an occurrence.
    Without it a hand-made request could tick off work that was never
    planned, and coverage stops being a number anyone can trust.
    """
    return day in occurrence_dates(schedule, day, day)


def next_due(schedule, today=None, horizon_days=400):
    """The next date this schedule falls due, for the Schedule tab. None
    when it has ended, or when nothing falls inside the horizon."""
    today = today or date.today()
    dates = occurrence_dates(schedule, today, today + timedelta(days=horizon_days))
    return dates[0] if dates else None
