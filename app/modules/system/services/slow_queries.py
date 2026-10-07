"""The slowest queries of the last 24 hours: live pg_stat_statements totals
minus the hourly sample saved nearest to 24 hours ago (lib/query_stats)."""
from datetime import datetime, timedelta

import psycopg2
from sqlalchemy import func
from sqlalchemy.exc import DBAPIError

from app.modules.core.shared.extensions import db
from app.modules.system.lib import query_stats
from app.modules.system.models import QueryStatSample

WINDOW = timedelta(hours=24)
SHOWN = 7
# Needs attention lists a query this slow on average, run at least this often.
SLOW_MS = 1000
SLOW_MIN_CALLS = 3


def _baseline(now):
    """(when the window starts, {queryid: (calls, total_ms)}). The sample from
    24 hours ago, else the oldest one; (None, {}) before the first sample."""
    start = (db.session.query(func.max(QueryStatSample.ts))
             .filter(QueryStatSample.ts <= now - WINDOW).scalar()
             or db.session.query(func.min(QueryStatSample.ts)).scalar())
    if start is None:
        return None, {}
    rows = QueryStatSample.query.filter_by(ts=start).all()
    return start, {row.queryid: (row.calls, row.total_ms) for row in rows}


def _ran(now):
    """(window start, {queryid: (calls, total_ms)}), or None while
    pg_stat_statements is off. Read in a savepoint so a failure leaves the page's
    transaction usable."""
    try:
        with db.session.begin_nested():
            cur = db.session.connection().connection.cursor()
            current = query_stats.read_totals(cur)
    except (psycopg2.Error, DBAPIError):
        return None
    if current is None:
        return None
    start, baseline = _baseline(now)
    return start, query_stats.window(current, baseline)


def _texts(queryids):
    try:
        with db.session.begin_nested():
            cur = db.session.connection().connection.cursor()
            cur.execute(query_stats.TEXTS_SQL, (list(queryids),))
            return dict(cur.fetchall())
    except (psycopg2.Error, DBAPIError):
        return {}


def _rows(ran, keep, limit):
    rows = [{'queryid': queryid, 'calls': calls, 'total_ms': total, 'mean_ms': total / calls}
            for queryid, (calls, total) in ran.items() if keep(calls, total / calls)]
    rows.sort(key=lambda row: row['mean_ms'], reverse=True)
    rows = rows[:limit]
    texts = _texts(row['queryid'] for row in rows) if rows else {}
    for row in rows:
        row['text'] = query_stats.short_text(texts.get(row['queryid']))
    return rows


def slowest(now=None, limit=SHOWN):
    """{'enabled': False} while pg_stat_statements is off; otherwise
    {'enabled', 'since', 'rows'}, rows slowest on average first. `since` is
    None when no hourly sample exists yet (totals since the last reset)."""
    now = now or datetime.utcnow()
    found = _ran(now)
    if found is None:
        return {'enabled': False}
    start, ran = found
    return {'enabled': True, 'since': start, 'rows': _rows(ran, lambda calls, mean: True, limit)}


def over_limit(now=None):
    """Queries over SLOW_MS on average with SLOW_MIN_CALLS runs in the window;
    empty while pg_stat_statements is off."""
    found = _ran(now or datetime.utcnow())
    if found is None:
        return []
    return _rows(found[1], lambda calls, mean: calls >= SLOW_MIN_CALLS and mean >= SLOW_MS, SHOWN)
