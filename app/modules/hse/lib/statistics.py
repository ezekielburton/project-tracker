"""
Statistics: what happened on site over a period, against the period before.
My performance measures the officer; this measures the site. Every figure is
worked out from the registers when shown; the weekly and monthly reports
read the same view model.
"""

from datetime import date
from decimal import Decimal

from app.modules.hse.lib.computed import next_due
from app.modules.hse.lib.flags import as_number
from app.modules.hse.lib.metrics import (
    parse_money, spend_by_area, spend_of, training_delivered,
)
from app.modules.hse.lib.performance import delta, trend_months
from app.modules.hse.lib.registers import BY_KEY, counts_as_done
from app.modules.hse.lib.schedule import add_months
from app.modules.hse.lib.spend import aed, amount_text, area_rows
from app.modules.hse.lib.vocab import OPEN_STATUSES


# Period choices: key -> (label, months covered).
PERIODS = {'month': ('This month', 1), 'quarter': ('Last 3 months', 3), 'year': ('Year', 12)}

INSPECTION_REGISTERS = ('general_inspection', 'vehicle_inspection', 'forklift_inspection')

# Rows shown per ranked list; the rest fold into "Other".
RANK_LIMIT = 6


# --- the period -------------------------------------------------------------

def period(view, year, today=None):
    """The window measured and the one before it, to the same point.
    This month and Last 3 months run to today; a year is Jan 1 to today for
    the current year, or the whole year for a past one. The previous window
    is the same span shifted back by the period's length."""
    today = today or date.today()
    view = view if view in PERIODS else 'month'
    label, months = PERIODS[view]
    if view == 'year':
        year = year if year and year <= today.year else today.year
        start = date(year, 1, 1)
        end = today if year == today.year else date(year, 12, 31)
        label = str(year) if year != today.year else f'{year} to date'
    else:
        end = today
        start = add_months(date(today.year, today.month, 1), -(months - 1))
    return {
        'view': view, 'year': start.year if view == 'year' else None,
        'label': label, 'start': start, 'end': end,
        'prev_start': add_months(start, -months), 'prev_end': add_months(end, -months),
        'months': months,
    }


def load_from(window):
    """Earliest date any section reads: the previous window or the chart's
    twelve months, whichever starts first."""
    chart_start = trend_months(window['end'])[0]['start']
    return min(window['prev_start'], chart_start)


def _in(entries, register, start, end):
    keys = (register,) if isinstance(register, str) else register
    return [e for e in entries if e.register in keys
            and e.entry_date is not None and start <= e.entry_date <= end]


def _data(entry, name):
    return (entry.data or {}).get(name)


# --- headline tiles ---------------------------------------------------------

def _is_near_miss(entry):
    """Anything not marked a near miss counts as an incident, so an
    unclassified entry is never dropped from the totals."""
    return _data(entry, 'event_class') == 'Near miss'


def _counts(entries, start, end, today):
    incidents = _in(entries, 'incidents', start, end)
    ltis = _in(entries, 'lost_time_injury', start, end)
    return {
        'incidents': sum(1 for e in incidents if not _is_near_miss(e)),
        'unclassified': sum(1 for e in incidents if not _data(e, 'event_class')),
        'near': sum(1 for e in incidents if _is_near_miss(e)),
        'first_aid': len(_in(entries, 'first_aid', start, end)),
        'lti': len(ltis),
        # Open cases count to today: the person is still off.
        'days_lost': sum(((e.closed_at or today) - e.entry_date).days for e in ltis),
    }


def days_since_last_lti(entries, today=None):
    """Days since the most recent lost time injury, or None if none is logged."""
    today = today or date.today()
    dates = [e.entry_date for e in entries
             if e.register == 'lost_time_injury' and e.entry_date and e.entry_date <= today]
    return (today - max(dates)).days if dates else None


def tiles(entries, window, today=None):
    """Incidents · Near misses · First aid · Lost time injuries · Days lost ·
    Days since the last LTI. Fewer is better except near misses, where more
    reported is the good result."""
    today = today or date.today()
    now = _counts(entries, window['start'], window['end'], today)
    before = _counts(entries, window['prev_start'], window['prev_end'], today)

    def tile(key, label, better, unit=''):
        return {'label': label, 'value': now[key], 'unit': unit,
                'delta': delta(now[key], before[key], better)}

    since = days_since_last_lti(entries, today)
    incidents = tile('incidents', 'Incidents', 'lower')
    if now['unclassified']:
        incidents['detail'] = f"{now['unclassified']} not marked incident or near miss"
    return [
        incidents,
        tile('near', 'Near misses', 'higher'),
        tile('first_aid', 'First aid cases', 'lower'),
        tile('lti', 'Lost time injuries', 'lower'),
        tile('days_lost', 'Days lost', 'lower', 'days'),
        {'label': 'Since the last LTI', 'value': since, 'unit': 'days', 'delta': None,
         'detail': None if since is not None else 'None logged'},
    ]


# --- incidents over time and breakdown --------------------------------------

def incident_series(entries, end):
    """Incidents and near misses per month, for the trailing twelve months."""
    out = []
    for month in trend_months(end):
        rows = _in(entries, 'incidents', month['start'], month['end'])
        out.append({
            'label': month['label'],
            'incidents': sum(1 for e in rows if not _is_near_miss(e)),
            'near': sum(1 for e in rows if _is_near_miss(e)),
        })
    return out


def ranked(counts, limit=RANK_LIMIT):
    """{label: value} as bars, largest first; the tail folds into Other.
    Shares are of the largest bar, so the top one fills its track."""
    items = sorted(((k, v) for k, v in counts.items() if v), key=lambda kv: (-kv[1], kv[0]))
    if len(items) > limit:
        items = items[:limit - 1] + [('Other', sum(v for _, v in items[limit - 1:]))]
    top = max((v for _, v in items), default=0)
    return [{'label': k, 'value': v, 'share': round(v * 100 / top) if top else 0}
            for k, v in items]


def _tally(rows, key):
    counts = {}
    for row in rows:
        label = key(row) or 'Not recorded'
        counts[label] = counts.get(label, 0) + 1
    return counts


def _label(obj, attr='label'):
    return getattr(obj, attr, None) if obj is not None else None


def incident_breakdown(entries, window):
    """Incidents and near misses in the window, by type, location and severity."""
    rows = _in(entries, 'incidents', window['start'], window['end'])
    return {
        'total': len(rows),
        'by_type': ranked(_tally(rows, lambda e: _data(e, 'incident_type'))),
        'by_location': ranked(_tally(rows, lambda e: _label(e.location))),
        'by_severity': ranked(_tally(rows, lambda e: e.severity)),
    }


# --- the areas --------------------------------------------------------------

def _has_issue(entry):
    """General inspections record an issue type; the others free text."""
    if entry.register == 'general_inspection':
        return bool(_data(entry, 'issue_type'))
    return bool(str(_data(entry, 'issues_found') or '').strip())


def inspections(entries, window):
    rows = _in(entries, INSPECTION_REGISTERS, window['start'], window['end'])
    by_register = []
    for key in INSPECTION_REGISTERS:
        mine = [e for e in rows if e.register == key]
        by_register.append({'label': BY_KEY[key].label, 'done': len(mine),
                            'issues': sum(1 for e in mine if _has_issue(e))})
    general = [e for e in rows if e.register == 'general_inspection' and _has_issue(e)]
    return {
        'done': len(rows),
        'issues': sum(1 for e in rows if _has_issue(e)),
        'open': sum(1 for e in entries
                    if e.register in INSPECTION_REGISTERS and e.status in OPEN_STATUSES),
        'by_register': by_register,
        'by_area': ranked(_tally(general, lambda e: _label(e.location))),
    }


def _money(rows, name='cost'):
    return sum((parse_money(_data(e, name)) or 0) for e in rows)


def fleet(entries, window):
    start, end = window['start'], window['end']
    km = {}
    for e in _in(entries, 'vehicle_mileage', start, end):
        value = as_number(_data(e, 'km'))
        if value:
            name = _label(e.asset) or 'Unknown vehicle'
            km[name] = km.get(name, 0) + value
    services = [e for e in _in(entries, 'vehicle_service', start, end)
                if e.status == 'Completed']
    return {
        'km': amount_text(sum(km.values())),
        'by_vehicle': [dict(r, text=amount_text(r['value'])) for r in ranked(km)],
        'services': len(services),
        'service_spend': amount_text(_money(services)),
    }


def pm_on_time(entries, start, end):
    """(on time, counted): PM jobs in the window done by the date the
    previous job set. A machine's first job has nothing to be late against."""
    pm = sorted((e for e in entries if e.register == 'machine_preventive'
                 and e.asset_id is not None and e.entry_date is not None),
                key=lambda e: (e.entry_date, e.id or 0))
    last, on_time, counted = {}, 0, 0
    reg = BY_KEY['machine_preventive']
    for entry in pm:
        previous = last.get(entry.asset_id)
        last[entry.asset_id] = entry
        if previous is None or not (start <= entry.entry_date <= end):
            continue
        due = next_due(previous, reg)
        if due is None:
            continue
        counted += 1
        on_time += entry.entry_date <= due
    return on_time, counted


def machines(entries, window):
    start, end = window['start'], window['end']
    jobs = _in(entries, 'machine_maintenance', start, end)
    downtime = sum((as_number(_data(e, 'downtime_hrs')) or 0) for e in jobs)
    on_time, counted = pm_on_time(entries, start, end)
    return {
        'jobs': len(jobs),
        'downtime': amount_text(downtime),
        'pm_done': len(_in(entries, 'machine_preventive', start, end)),
        'pm_on_time': on_time,
        'pm_counted': counted,
        'pm_percent': round(on_time * 100 / counted) if counted else None,
    }


def _issued_moves(entry, start, end):
    total = 0
    for move in _data(entry, 'moves') or ():
        try:
            day = date.fromisoformat(str(move.get('date')))
        except (TypeError, ValueError):
            continue
        if move.get('kind') == 'issued' and start <= day <= end:
            total += as_number(move.get('qty')) or 0
    return total


def stores(entries, window):
    start, end = window['start'], window['end']
    ppe = {}
    for e in _in(entries, 'ppe_register', start, end):
        name = _data(e, 'ppe_type') or 'Not recorded'
        ppe[name] = ppe.get(name, 0) + (as_number(_data(e, 'qty')) or 1)
    materials = {}
    for e in entries:
        if e.register == 'materials_in_stock':
            qty = _issued_moves(e, start, end)
            if qty:
                materials[_data(e, 'item') or e.ref] = qty
    requests = _in(entries, 'material_request', start, end)
    statuses = BY_KEY['material_request'].statuses
    return {
        'ppe': ranked(ppe),
        'ppe_total': sum(ppe.values()),
        'materials': ranked(materials),
        'requests': len(requests),
        'by_status': [{'label': s, 'value': sum(1 for e in requests if e.status == s)}
                      for s in statuses],
    }


def training(entries, window):
    start, end = window['start'], window['end']
    delivered = training_delivered(entries, start, end)
    inductions = [e for e in _in(entries, 'induction_training', start, end)
                  if e.status == 'Completed']
    talks = [e for e in _in(entries, 'toolbox_talk', start, end) if counts_as_done(e)]
    return {
        'sessions': delivered['sessions'],
        'attendees': delivered['attendees'],
        'inductions': len(inductions),
        'talks': len(talks),
        'by_type': ranked({b['label']: b['attendees'] for b in delivered['by_type']}),
    }


# --- spend ------------------------------------------------------------------

def _spent(rows, start, end):
    return sum((spend_of(r) for r in rows
                if r.entry_date is not None and start <= r.entry_date <= end), Decimal(0))


def spend(rows, window):
    """Spend in the window against the one before, by area, and month by
    month for the chart's twelve months beside the same month a year
    earlier. `rows` come from query.spend_entries(), like the Overview's.
    Chart values are AED thousands so the axis labels stay short."""
    now = _spent(rows, window['start'], window['end'])
    before = _spent(rows, window['prev_start'], window['prev_end'])
    series = []
    for month in trend_months(window['end']):
        year_ago = (add_months(month['start'], -12), add_months(month['end'], -12))
        series.append({
            'label': month['label'],
            'spend': float(_spent(rows, month['start'], month['end'])) / 1000,
            'before': float(_spent(rows, *year_ago)) / 1000,
        })
    split = spend_by_area(rows, window['start'], window['end'])
    areas = area_rows(split)
    ranked_areas = sorted(zip(split['areas'], areas), key=lambda pair: -pair[0]['amount'])
    return {
        'total': aed(now),
        'previous': aed(before),
        # Whole dirhams on the tile so the figure fits; neither more nor less
        # spend is better, so it shows no verdict.
        'tile': {'label': 'Spend', 'value': aed(round(now), unit=False), 'unit': 'AED',
                 'delta': {'improved': None, 'from': aed(round(before), unit=False),
                           'neutral': True}},
        'areas': areas,
        # The biggest three, for the reports' Spend card.
        'top': [row for raw, row in ranked_areas if raw['amount']][:3],
        'series': series,
    }


# --- the page ---------------------------------------------------------------

def year_choices(today=None, first_year=None):
    """Years offered in the picker, newest first."""
    today = today or date.today()
    first = min(first_year or today.year, today.year)
    return list(range(today.year, first - 1, -1))


def view_model(entries, window, today=None, spend_rows=()):
    """Everything the page draws. `entries` must reach back to load_from();
    `spend_rows` are query.spend_entries()."""
    today = today or date.today()
    return {
        'spend': spend(spend_rows, window),
        'window': window,
        'tiles': tiles(entries, window, today),
        'series': incident_series(entries, window['end']),
        'breakdown': incident_breakdown(entries, window),
        'inspections': inspections(entries, window),
        'fleet': fleet(entries, window),
        'machines': machines(entries, window),
        'stores': stores(entries, window),
        'training': training(entries, window),
    }
