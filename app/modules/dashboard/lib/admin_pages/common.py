"""Helpers the admin page cards share: page links, next-run labels, tiles and bar widths."""
from datetime import datetime, timedelta

from flask import url_for

from app.modules.dashboard.lib.rails import PAGES
from app.modules.system.lib import fmt
from app.modules.system.services import health
from app.modules.system.services.snapshot import parse_time, read_snapshot

# The badge reads Live while the snapshot is younger than this.
LIVE_WITHIN = timedelta(minutes=3)


def link(page_key):
    page = PAGES[page_key]
    return {'label': page.label, 'url': url_for(page.endpoint)}


def when(moment, now):
    """'in under 1 min', 'in 2 min', 'today 23:00', 'Sun 04:00' for a naive-UTC moment."""
    minutes = (moment - now).total_seconds() / 60
    if minutes < 1:
        return 'in under 1 min'
    if minutes < 60:
        return f'in {max(int(minutes), 0)} min'
    local, today = fmt.local(moment), fmt.local(now)
    if local.date() == today.date():
        return f"today {local:%H:%M}"
    if local.date() == today.date() + timedelta(days=1):
        return f"tomorrow {local:%H:%M}"
    return f"{local:%a %H:%M}"


def badge(snapshot=None, now=None):
    """The status badge on every admin page: {state, text, age, day}. Live while
    the snapshot is under LIVE_WITHIN old, else how many minutes since it updated.
    `age` (seconds) lets the page script keep counting without asking again."""
    snapshot = read_snapshot() if snapshot is None else snapshot
    now = now or datetime.utcnow()
    today = fmt.local(now)
    day = f'{today:%a} {today.day} {today:%b}'
    taken = parse_time(snapshot.get('taken_at'))
    if taken is None:
        return {'state': 'none', 'text': 'No data yet', 'age': None, 'day': day}
    age = max(int((now - taken).total_seconds()), 0)
    if age < LIVE_WITHIN.total_seconds():
        return {'state': 'live', 'text': f'Live · {day}', 'age': age, 'day': day}
    return {'state': 'stale', 'text': f'Updated {max(age // 60, 1)} min ago', 'age': age, 'day': day}


def state(value, warn, bad, high_is_bad=True):
    if value is None:
        return health.GREY
    if high_is_bad:
        return health.RED if value >= bad else health.AMBER if value >= warn else health.GREEN
    return health.RED if value <= bad else health.AMBER if value <= warn else health.GREEN


def tile(label, value, unit=None, sub=None, pct=None, tone=None, text=False, sub_tone=None):
    """One vital tile: a big value with its unit, an optional meter (pct, tone) and a line under it."""
    return {'label': label, 'value': value, 'unit': unit, 'sub': sub, 'pct': pct,
            'tone': tone, 'text': text, 'sub_tone': sub_tone}


def split(label):
    """'412 MB' -> ('412', 'MB'); None -> (None, None)."""
    if label is None:
        return None, None
    value, _, unit = label.partition(' ')
    return value, unit or None


def bar_rows(rows, label_key, value_key, show):
    """[{label, pct, value}] for horizontal bars, each as a % of the largest."""
    top = max((row[value_key] or 0 for row in rows), default=0) or 1
    return [{'label': row[label_key], 'pct': round(100 * (row[value_key] or 0) / top),
             'value': show(row)} for row in rows]
