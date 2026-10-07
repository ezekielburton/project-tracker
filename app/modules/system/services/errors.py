"""What the admin Errors page shows: errors and warnings read from the app
log (kept 7 days), 500s from request metrics, and NAS/background failures."""
from datetime import datetime, timedelta

from sqlalchemy import func

from app.modules.core.shared.extensions import db
from app.modules.system.lib import fmt
from app.modules.system.models import AppLogEvent, RequestMetric
from app.modules.system.services import health

WINDOW = timedelta(hours=24)
GROUP_WINDOW = timedelta(days=7)
GROUPS_SHOWN = 12
LINES_SHOWN = 5
ROUTES_SHOWN = 8
TAIL_SHOWN = 20
_LEVELS = ('error', 'warning')


def tiles(now=None):
    """Errors and warnings, 500s with their share of requests, and background failures, all 24 hours."""
    now = now or datetime.utcnow()
    since = now - WINDOW
    levels = dict(db.session.query(AppLogEvent.level, func.count())
                  .filter(AppLogEvent.ts >= since, AppLogEvent.level.in_(_LEVELS))
                  .group_by(AppLogEvent.level).all())
    requests, failed = (db.session.query(func.count(), func.count().filter(RequestMetric.status >= 500))
                        .filter(RequestMetric.ts >= since).one())
    return {'errors': levels.get('error', 0), 'warnings': levels.get('warning', 0),
            'http_500': failed, 'http_500_pct': round(100 * failed / requests, 2) if requests else None,
            'failures': health.background_failures(since)}


def _lines(signatures, since):
    """{signature: its latest LINES_SHOWN events, newest first}."""
    newest = func.row_number().over(partition_by=AppLogEvent.signature, order_by=AppLogEvent.ts.desc())
    ranked = (db.session.query(AppLogEvent.signature, AppLogEvent.ts, AppLogEvent.level,
                               AppLogEvent.message, AppLogEvent.detail, newest.label('n'))
              .filter(AppLogEvent.signature.in_(signatures), AppLogEvent.ts >= since,
                      AppLogEvent.level.in_(_LEVELS)).subquery())
    rows = db.session.query(ranked).filter(ranked.c.n <= LINES_SHOWN).order_by(ranked.c.ts.desc()).all()
    found = {}
    for row in rows:
        found.setdefault(row.signature, []).append(row)
    return found


def groups(now=None, limit=GROUPS_SHOWN):
    """[{signature, error, message, source, count, first, last, lines}] over 7 days,
    the most recent first; `error` is True when any repeat was an error."""
    now = now or datetime.utcnow()
    since = now - GROUP_WINDOW
    rows = (db.session.query(AppLogEvent.signature, func.bool_or(AppLogEvent.level == 'error'),
                             func.max(AppLogEvent.message), func.max(AppLogEvent.source), func.count(),
                             func.min(AppLogEvent.ts), func.max(AppLogEvent.ts))
            .filter(AppLogEvent.ts >= since, AppLogEvent.level.in_(_LEVELS))
            .group_by(AppLogEvent.signature).order_by(func.max(AppLogEvent.ts).desc()).limit(limit).all())
    lines = _lines([row[0] for row in rows], since) if rows else {}
    result = []
    for signature, error, message, source, count, first, last in rows:
        result.append({
            'signature': signature, 'error': bool(error), 'message': message, 'source': source,
            'count': count, 'first': fmt.day_time(first, now), 'last': fmt.day_time(last, now),
            'lines': [{'time': fmt.day_time(line.ts, now), 'level': line.level, 'message': line.message,
                       'detail': line.detail} for line in lines.get(signature, [])],
        })
    return result


def routes_500(now=None, limit=ROUTES_SHOWN):
    """[{method, route, count, last}]: routes that answered 5xx in 7 days, most first."""
    now = now or datetime.utcnow()
    rows = (db.session.query(RequestMetric.method, RequestMetric.route, func.count(), func.max(RequestMetric.ts))
            .filter(RequestMetric.ts >= now - GROUP_WINDOW, RequestMetric.status >= 500)
            .group_by(RequestMetric.method, RequestMetric.route)
            .order_by(func.count().desc(), func.max(RequestMetric.ts).desc()).limit(limit).all())
    return [{'method': method, 'route': route, 'count': count, 'last': fmt.day_time(last, now)}
            for method, route, count, last in rows]


def tail(now=None, limit=TAIL_SHOWN):
    """The latest app-log lines of any level, newest first."""
    now = now or datetime.utcnow()
    rows = AppLogEvent.query.order_by(AppLogEvent.ts.desc(), AppLogEvent.id.desc()).limit(limit).all()
    return [{'time': fmt.day_time(row.ts, now), 'level': row.level, 'message': row.message} for row in rows]
