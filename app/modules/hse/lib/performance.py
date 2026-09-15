"""
My performance — the view model behind the page and the PDF.

Every figure comes from lib/metrics.py; nothing is counted twice here. The
page's job is to arrange them and to say, in each case, what "better" means:
a falling average time to close is an improvement, and an arrow that does not
know that is worse than no arrow.
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

# Open actions, bucketed by how long they have been open. The edges are days.
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
    """The window the tiles measure, and the one before it to compare with.

    Month is the calendar month. Year is the trailing twelve months ending
    with the anchor's month — not January to December, because a review in
    September should read the twelve months he actually worked.
    """
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


def trend_months(end, count=TREND_MONTHS):
    """The months the two charts run over — always the trailing twelve,
    whichever view the tiles are showing. The tiles are the period; the
    charts are the context around it."""
    out = []
    for offset in range(count - 1, -1, -1):
        first = _month_start(_shift_months(_month_start(end), -offset))
        out.append({'start': first, 'end': _month_end(first),
                    'label': first.strftime('%b')})
    return out


# --- the four tiles -------------------------------------------------------

def _delta(now, before, better):
    """The comparison line under a tile.

    `better` is 'higher' or 'lower', so a falling average time to close reads
    as the improvement it is. None when there is nothing to compare against —
    a first period gets no arrow rather than a fake one.
    """
    if now is None or before is None:
        return None
    if now == before:
        return {'improved': None, 'from': before}
    improved = now > before if better == 'higher' else now < before
    return {'improved': improved, 'from': before}


def tiles(schedules, entries, window, today=None):
    """Actions closed on time · Average time to close · Inspection coverage ·
    Training delivered. Compliance health is a panel, not a tile — it needs
    the lapse named beside it to mean anything."""
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

    # Days the closed work spent parked with someone else — the honest
    # footnote under an average that would otherwise look like his alone.
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
    """Planned against completed, month by month. Both bars come from the
    calendar's own coverage, so the chart and the tile cannot disagree."""
    out = []
    for month in months:
        cover = done_vs_due(schedules, entries, month['start'], month['end'], today)
        out.append({'label': month['label'],
                    'planned': cover['due'], 'done': cover['done']})
    return out


def age_series(entries, months):
    """Average days to close, month by month. A month with no closures is a
    gap in the line rather than a zero — nothing closed is not instant."""
    return [{'label': m['label'],
             'days': average_days_to_close(entries, m['start'], m['end'])['days']}
            for m in months]


# --- the three panels -----------------------------------------------------

def reporting(entries, window):
    """Near misses per incident, with the warning that makes it readable.

    The note is not decoration. A manager reading a rising number as a worse
    site punishes the exact behaviour the officer is building.
    """
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
    """Renewals in the period, and how many landed before the old one ran out.

    A renewal is a later entry in Compliance & renewals for the same
    certificate. Certificates are identified by compliance_item_id — a
    reference row — so renaming one keeps its history rather than splitting
    it. An entry with no certificate set is skipped.
    """
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
    """Valid today, renewed before expiry, and what lapsed — named.

    The page shows the lapse. A compliance number with the failure hidden
    underneath it is worth nothing in the room.
    """
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
    """Open actions bucketed by age, oldest named underneath.

    Age is days open, not days owned: the question here is how long the site
    has been living with it, which is true whoever is holding it up.
    """
    today = today or date.today()
    open_rows = []
    for entry in entries:
        register = BY_KEY.get(entry.register)
        if register is None or register.status_source != 'stored':
            continue
        # The same open set the rail badges count, so the two can never
        # disagree — and so a completed induction is not an open action.
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
    """The service levels, worst first, so the report can show the rule it is
    judging against instead of asking the reader to take it on trust."""
    from app.modules.hse.lib.computed import SEVERITY_SCORE, SLA_DAYS
    return [(label, SLA_DAYS[label])
            for label in sorted(SLA_DAYS, key=lambda s: -SEVERITY_SCORE[s])]


def schedule_coverage(schedules, entries, window, today=None):
    """Coverage per schedule, so a single failing round is visible instead of
    being averaged away by eleven that went fine."""
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
    """Compliance items falling due inside the window, soonest first."""
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
    """The report's closing notes, written from the figures rather than about
    them. Each one only appears when its number exists, so the page never
    claims something the data cannot support.
    """
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
    """What closed in the period and how much of it met its service level,
    split by severity — the breakdown behind the on-time percentage.

    A severity with nothing closed is left out rather than shown as 0%.
    """
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
