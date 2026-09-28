"""
My performance: the view model for the page and its PDF report.

Figures come from lib/metrics.py; this module arranges them and records,
per figure, whether higher or lower is better.
"""

from calendar import monthrange
from datetime import date

from app.modules.hse.lib.computed import days_open, days_waiting
from app.modules.hse.lib.metrics import (
    average_days_to_close, closed_on_time_rate, compliance_health,
    done_vs_due, near_miss_ratio, training_delivered,
)
from app.modules.hse.lib.registers import BY_KEY
from app.modules.hse.lib.vocab import OPEN_STATUSES

VIEWS = ('month', 'year')
TREND_MONTHS = 12

# Age buckets for open actions: (label, from day, to day exclusive, tone).
AGE_BUCKETS = (
    ('Under a week', 0, 7, 'good'),
    ('One to four weeks', 7, 28, 'warn'),
    ('One to three months', 28, 90, 'late'),
    ('Over three months', 90, None, 'bad'),
)


def _month_start(day):
    return day.replace(day=1)


def _month_end(day):
    return day.replace(day=monthrange(day.year, day.month)[1])


def _shift_months(day, months):
    """The same day-of-month `months` away, clamped to a short month."""
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def period(view, anchor):
    """The window the tiles measure, plus the previous one to compare with.
    Month is the calendar month; Year is the trailing twelve months ending
    with the anchor's month (not the calendar year)."""
    view = view if view in VIEWS else 'month'
    end = _month_end(anchor)
    if view == 'month':
        start = _month_start(anchor)
        prev_start = _month_start(_shift_months(start, -1))
        prev_end = _month_end(prev_start)
        label = start.strftime('%B %Y')
    else:
        start = _month_start(_shift_months(end, -(TREND_MONTHS - 1)))
        prev_end = _month_end(_shift_months(start, -1))
        prev_start = _month_start(_shift_months(prev_end, -(TREND_MONTHS - 1)))
        label = f"{start.strftime('%b %Y')} – {end.strftime('%b %Y')}"
    return {'view': view, 'start': start, 'end': end, 'label': label,
            'prev_start': prev_start, 'prev_end': prev_end}


def navigation(window, today):
    """Prev/next targets and whether the current period is shown. Both views
    anchor on the window's end month; Month steps 1, Year steps 12. Forward
    never passes the current month."""
    step = 1 if window['view'] == 'month' else TREND_MONTHS
    current = _month_start(today)
    shown = _month_start(window['end'])
    forward = min(_shift_months(shown, step), current) if shown < current else None
    return {
        'month': shown.strftime('%Y-%m'),
        'prev': _shift_months(shown, -step).strftime('%Y-%m'),
        'next': forward.strftime('%Y-%m') if forward else None,
        'is_current': shown == current,
    }


def trend_months(end, count=TREND_MONTHS):
    """The months the charts cover: always the trailing twelve, whatever
    view the tiles show."""
    out = []
    for offset in range(count - 1, -1, -1):
        first = _month_start(_shift_months(_month_start(end), -offset))
        out.append({'start': first, 'end': _month_end(first),
                    'label': first.strftime('%b')})
    return out


# --- the four tiles -------------------------------------------------------

def _delta(now, before, better):
    """The comparison under a tile. `better` is 'higher' or 'lower'. None
    when either value is missing, so no arrow is drawn."""
    if now is None or before is None:
        return None
    if now == before:
        return {'improved': None, 'from': before}
    improved = now > before if better == 'higher' else now < before
    return {'improved': improved, 'from': before}


def tiles(schedules, entries, window, today=None):
    """Actions closed on time · Average time to close · Inspection coverage ·
    Training delivered. Compliance health is a separate panel, since it
    names the lapsed items."""
    start, end = window['start'], window['end']
    prev = (window['prev_start'], window['prev_end'])

    on_time = closed_on_time_rate(entries, start, end, today)
    on_time_prev = closed_on_time_rate(entries, *prev, today)

    speed = average_days_to_close(entries, start, end)
    speed_prev = average_days_to_close(entries, *prev)

    cover = done_vs_due(schedules, entries, start, end, today)
    cover_prev = done_vs_due(schedules, entries, *prev, today)

    taught = training_delivered(entries, start, end)
    taught_prev = training_delivered(entries, *prev)

    # Closed entries that spent time waiting on others; footnote under the average.
    closed = [e for e in entries
              if e.closed_at is not None and start <= e.closed_at <= end]
    parked = sum(1 for e in closed if days_waiting(e, today) > 0)

    return [{
        'key': 'on_time',
        'value': on_time['percent'],
        'unit': '%',
        'label': 'Actions closed on time',
        'detail': f"{on_time['judged']} actions judged",
        'delta': _delta(on_time['percent'], on_time_prev['percent'], 'higher'),
        'delta_unit': '%',
    }, {
        'key': 'speed',
        'value': speed['days'],
        'unit': 'days',
        'label': 'Average time to close',
        'detail': f'{parked} of them waiting on others' if parked else None,
        'delta': _delta(speed['days'], speed_prev['days'], 'lower'),
        'delta_unit': '',
    }, {
        'key': 'coverage',
        'value': cover['percent'],
        'unit': '%',
        'label': 'Inspection coverage',
        'detail': f"{cover['done']} of {cover['due']} planned",
        'delta': _delta(cover['percent'], cover_prev['percent'], 'higher'),
        'delta_unit': '%',
    }, {
        'key': 'training',
        'value': taught['sessions'],
        'unit': 'sessions',
        'label': 'Training delivered',
        'detail': f"{taught['attendees']} attendees",
        'delta': _delta(taught['sessions'], taught_prev['sessions'], 'higher'),
        'delta_unit': '',
    }]


# --- the two charts -------------------------------------------------------

def coverage_series(schedules, entries, months, today=None):
    """Planned vs completed, per month, from the same coverage as the tile."""
    out = []
    for month in months:
        cover = done_vs_due(schedules, entries, month['start'], month['end'], today)
        out.append({'label': month['label'],
                    'planned': cover['due'], 'done': cover['done']})
    return out


def age_series(entries, months):
    """Average days to close, per month. A month with no closures is None
    (a gap in the line, not zero)."""
    return [{'label': m['label'],
             'days': average_days_to_close(entries, m['start'], m['end'])['days']}
            for m in months]


# --- the three panels -----------------------------------------------------

def reporting(entries, window):
    """Near misses per incident for the period, with its delta. Higher is
    better (more hazards reported before harm)."""
    now = near_miss_ratio(entries, window['start'], window['end'])
    before = near_miss_ratio(entries, window['prev_start'], window['prev_end'])
    return {
        'ratio': now['ratio'],
        'near_misses': now['near_misses'],
        'incidents': now['incidents'],
        'unclassified': now['unclassified'],
        'delta': _delta(now['ratio'], before['ratio'], 'higher'),
    }


def _renewals(entries, start, end):
    """Renewals in the period, and how many landed before the previous one
    expired. A renewal is a later compliance_renewal entry with the same
    compliance_item_id; entries without one are skipped."""
    rows = [e for e in entries
            if e.register == 'compliance_renewal' and e.entry_date is not None]
    by_item = {}
    for entry in rows:
        item_id = entry.compliance_item_id
        if item_id is not None:
            by_item.setdefault(item_id, []).append(entry)

    renewed = on_time = 0
    for group in by_item.values():
        group.sort(key=lambda e: e.entry_date)
        for previous, current in zip(group, group[1:]):
            if not start <= current.entry_date <= end:
                continue
            renewed += 1
            if previous.due_at and current.entry_date <= previous.due_at:
                on_time += 1
    return {'renewed': renewed, 'on_time': on_time}


def compliance_panel(entries, window, today=None):
    """Compliance panel: valid today, renewals, and the items that lapsed in
    the period (first three named)."""
    today = today or date.today()
    health = compliance_health(entries, today)
    lapsed = [e for e in health['lapsed']
              if window['start'] <= e.due_at <= window['end']]
    lapsed.sort(key=lambda e: e.due_at)
    return {
        'valid': health['valid'],
        'total': health['total'],
        'percent': health['percent'],
        'renewals': _renewals(entries, window['start'], window['end']),
        'lapsed_count': len(lapsed),
        'lapsed': [{'ref': e.ref,
                    'item': e.compliance_item.label if e.compliance_item else e.ref,
                    'due_at': e.due_at} for e in lapsed[:3]],
    }


def open_by_age(entries, today=None):
    """Open actions bucketed by age, plus the oldest one. Age is days open,
    including time waiting on others."""
    today = today or date.today()
    open_rows = []
    for entry in entries:
        register = BY_KEY.get(entry.register)
        if register is None or register.status_source != 'stored':
            continue
        # Same open set as the rail badges (OPEN_STATUSES).
        if entry.closed_at is not None or entry.status not in OPEN_STATUSES:
            continue
        age = days_open(entry, today)
        if age is not None:
            open_rows.append((age, entry))

    buckets = []
    for label, low, high, tone in AGE_BUCKETS:
        rows = [e for age, e in open_rows
                if age >= low and (high is None or age < high)]
        buckets.append({'label': label, 'tone': tone, 'count': len(rows)})

    total = sum(b['count'] for b in buckets)
    for bucket in buckets:
        bucket['percent'] = round(bucket['count'] * 100 / total) if total else 0

    oldest = max(open_rows, key=lambda pair: pair[0], default=None)
    return {
        'buckets': buckets,
        'total': total,
        'oldest': None if oldest is None else {
            'ref': oldest[1].ref,
            'days': oldest[0],
            'waiting_on': (oldest[1].waiting_on.name
                           if oldest[1].waiting_on_id and oldest[1].waiting_on
                           else None),
        },
    }


# --- the report's extra sections ------------------------------------------

def sla_table():
    """(severity, SLA days) pairs, worst severity first, for the report."""
    from app.modules.hse.lib.computed import SEVERITY_SCORE, SLA_DAYS
    return [(label, SLA_DAYS[label])
            for label in sorted(SLA_DAYS, key=lambda s: -SEVERITY_SCORE[s])]


def schedule_coverage(schedules, entries, window, today=None):
    """Coverage per schedule, worst first, so one failing schedule is not
    hidden by the average."""
    from app.modules.hse.lib.schedule import coverage

    rows = []
    for schedule in schedules:
        cover = coverage([schedule], entries, window['start'], window['end'], today)
        if not cover['due']:
            continue
        rows.append({'label': schedule.label, 'due': cover['due'],
                     'done': cover['done'], 'percent': cover['percent'] or 0})
    rows.sort(key=lambda r: (r['percent'], -r['due']))
    return rows


def expiring_next(entries, today=None, days=30):
    """Compliance items falling due within `days`, soonest first."""
    from app.modules.hse.lib.computed import days_to_expiry

    today = today or date.today()
    rows = []
    for entry in entries:
        register = BY_KEY.get(entry.register)
        if register is None or register.status_source != 'expiry':
            continue
        left = days_to_expiry(entry, today)
        if left is None or not 0 <= left <= days:
            continue
        rows.append({'item': (entry.compliance_item.label if entry.compliance_item
                              else register.label),
                     'ref': entry.ref, 'due_at': entry.due_at, 'days': left})
    rows.sort(key=lambda r: r['due_at'])
    return rows


def read_outs(tile_rows, reporting_row, compliance_row, ageing_row):
    """The report's closing notes (up to four), generated from the figures.
    A note appears only when its figure exists."""
    by_key = {t['key']: t for t in tile_rows}
    out = []

    coverage_tile = by_key['coverage']
    if coverage_tile['value'] is not None:
        strong = coverage_tile['value'] >= 90
        out.append({
            'title': 'The programme ran' if strong else 'The programme slipped',
            'body': (f"Of the planned inspection programme, {coverage_tile['detail']} "
                     f"were completed. "
                     + ('Coverage at this level means the schedule is being worked, '
                        'not just published.' if strong else
                        'The gap is in the schedule coverage table — worth reading '
                        'per schedule rather than as one average.')),
        })

    on_time = by_key['on_time']
    if on_time['value'] is not None:
        out.append({
            'title': 'Actions are closing on time' if on_time['value'] >= 80
                     else 'Closing times need attention',
            'body': (f"{on_time['value']}% of actions closed inside the service level "
                     f"for their severity, over {on_time['detail']}. Time parked with "
                     f"another department is excluded."),
        })

    if reporting_row['ratio'] is not None:
        out.append({
            'title': 'Reporting is healthy' if reporting_row['ratio'] >= 1
                     else 'Near-miss reporting is thin',
            'body': (f"{reporting_row['near_misses']} near misses to "
                     f"{reporting_row['incidents']} incidents. A higher ratio is the "
                     f"better result — it means hazards are being raised before "
                     f"anyone is hurt."),
        })

    if compliance_row['lapsed_count']:
        out.append({
            'title': 'Something lapsed',
            'body': (f"{compliance_row['lapsed_count']} compliance item(s) expired in "
                     f"this period. They are named on this page rather than netted "
                     f"off the percentage."),
        })
    elif ageing_row['total']:
        out.append({
            'title': 'Nothing lapsed',
            'body': (f"Every tracked compliance item was renewed before it expired. "
                     f"{ageing_row['total']} action(s) remain open."),
        })

    return out[:4]


def closed_by_severity(entries, window, today=None):
    """Closed and closed-on-time counts per severity for the period. A
    severity with nothing closed is left out."""
    from app.modules.hse.lib.computed import SEVERITY_SCORE, closed_on_time

    start, end = window['start'], window['end']
    rows = {}
    for entry in entries:
        if entry.closed_at is None or not start <= entry.closed_at <= end:
            continue
        if entry.severity not in SEVERITY_SCORE:
            continue
        row = rows.setdefault(entry.severity, {'label': entry.severity,
                                               'closed': 0, 'on_time': 0})
        row['closed'] += 1
        if closed_on_time(entry, today):
            row['on_time'] += 1

    out = sorted(rows.values(), key=lambda r: -SEVERITY_SCORE[r['label']])
    for row in out:
        row['percent'] = round(row['on_time'] * 100 / row['closed'])
    return out
