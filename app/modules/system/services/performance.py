"""What the admin Performance page shows, from request metrics: response
times, errors, page load by module, the slowest routes and the workers."""
from datetime import datetime, timedelta

from sqlalchemy import func

from app.modules.core.shared.extensions import db
from app.modules.system.lib import fmt, modules
from app.modules.system.models import RequestMetric
from app.modules.system.services import health
from app.modules.system.services.snapshot import parse_time

WINDOW = timedelta(hours=24)
PAGE_WINDOW = timedelta(days=7)
P95_TARGET_MS = 800
ERROR_WARN_PCT, ERROR_BAD_PCT = 1, 5
MODULES_SHOWN = 8
ROUTES_SHOWN = 7
ROUTE_MIN_CALLS = 3

_P95 = func.percentile_cont(0.95).within_group(RequestMetric.duration_ms)


def _round(value):
    return None if value is None else int(round(value))


def summary(snapshot, now=None):
    """Requests, average and p95 response time, the 5xx rate (24h), open SSE streams."""
    now = now or datetime.utcnow()
    count, avg, p95, errors = (db.session.query(
        func.count(), func.avg(RequestMetric.duration_ms), _P95,
        func.count().filter(RequestMetric.status >= 500))
        .filter(RequestMetric.ts >= now - WINDOW).one())
    workers = snapshot.get('workers') or {}
    result = {'requests': count, 'avg_ms': _round(avg), 'p95_ms': _round(p95), 'errors': errors,
              'error_pct': round(100 * errors / count, 1) if count else None,
              'sse_open': health.sse_open(now), 'workers': workers.get('total')}
    result['p95_state'] = (health.GREY if p95 is None else
                           health.GREEN if p95 < P95_TARGET_MS else health.AMBER)
    result['p95_pct'] = None if p95 is None else min(round(100 * p95 / P95_TARGET_MS), 100)
    pct = result['error_pct']
    result['error_state'] = (health.GREY if pct is None else health.RED if pct >= ERROR_BAD_PCT
                             else health.AMBER if pct >= ERROR_WARN_PCT else health.GREEN)
    return result


def response_series(now=None):
    """{'avg': [(moment, ms)], 'p95': [...]}, one point per hour over 24 hours."""
    now = now or datetime.utcnow()
    hour = func.date_trunc('hour', RequestMetric.ts)
    rows = (db.session.query(hour, func.avg(RequestMetric.duration_ms), _P95)
            .filter(RequestMetric.ts >= now - WINDOW).group_by(hour).order_by(hour).all())
    middle = timedelta(minutes=30)
    return {'avg': [(start + middle, float(avg)) for start, avg, _ in rows],
            'p95': [(start + middle, float(p95)) for start, _, p95 in rows]}


def page_load_by_module(now=None, limit=MODULES_SHOWN):
    """[{module, median_ms, loads}]: server time for a whole page, median over 7 days, slowest first."""
    now = now or datetime.utcnow()
    pages = (db.session.query(modules.module_column(RequestMetric.blueprint).label('module'),
                              RequestMetric.duration_ms.label('ms'))
             .filter(RequestMetric.page.is_(True), RequestMetric.status == 200,
                     RequestMetric.ts >= now - PAGE_WINDOW).subquery())
    median = func.percentile_cont(0.5).within_group(pages.c.ms)
    rows = (db.session.query(pages.c.module, median, func.count())
            .group_by(pages.c.module).order_by(median.desc()).limit(limit).all())
    return [{'module': module, 'median_ms': _round(ms), 'loads': loads} for module, ms, loads in rows]


def slowest_routes(now=None, limit=ROUTES_SHOWN):
    """[{method, route, avg_ms, p95_ms, calls}] over 24 hours, slowest on average
    first; a route needs ROUTE_MIN_CALLS calls to be listed."""
    now = now or datetime.utcnow()
    avg = func.avg(RequestMetric.duration_ms)
    rows = (db.session.query(RequestMetric.method, RequestMetric.route, avg, _P95, func.count())
            .filter(RequestMetric.ts >= now - WINDOW)
            .group_by(RequestMetric.method, RequestMetric.route)
            .having(func.count() >= ROUTE_MIN_CALLS)
            .order_by(avg.desc()).limit(limit).all())
    return [{'method': method, 'route': route, 'avg_ms': _round(a), 'p95_ms': _round(p), 'calls': calls}
            for method, route, a, p, calls in rows]


def workers(snapshot, now=None):
    """Gunicorn workers alive, worker starts in 24 hours, the longest request and
    the p95 wait for a worker (needs nginx's X-Request-Start)."""
    now = now or datetime.utcnow()
    since = now - WINDOW
    found = snapshot.get('workers')
    starts = [moment for moment in snapshot.get('worker_starts') or []
              if (parse_time(moment) or since) > since]
    longest = (db.session.query(RequestMetric.duration_ms, RequestMetric.route)
               .filter(RequestMetric.ts >= since).order_by(RequestMetric.duration_ms.desc()).first())
    queue = (db.session.query(func.percentile_cont(0.95).within_group(RequestMetric.queue_ms))
             .filter(RequestMetric.ts >= since, RequestMetric.queue_ms.isnot(None)).scalar())
    return {
        'alive': found['alive'] if found else None,
        'total': found['total'] if found else None,
        'state': (health.GREY if not found else
                  health.AMBER if found['alive'] < found['total'] else health.GREEN),
        'restarts': len(starts) if found else None,
        'longest': None if longest is None else {'time': fmt.ms(longest[0]), 'route': longest[1]},
        'queue_p95': fmt.ms(queue),
    }
