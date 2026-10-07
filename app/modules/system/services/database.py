"""What the admin Database page shows: size and growth, connections, cache
hits, the last backup, the largest tables, the slowest queries and
maintenance. Postgres statistics are read live; history comes from the
collector's samples."""
from datetime import datetime, timedelta

from sqlalchemy import func, text

from app.modules.core.shared.extensions import db
from app.modules.system.lib import fmt
from app.modules.system.models import SystemSample
from app.modules.system.services import health, slow_queries

GROWTH_WINDOW = timedelta(days=30)
TABLES_SHOWN = 7
CACHE_WARN_PCT = 95
DEAD_WARN_PCT = 10


def _scalar(sql):
    return db.session.execute(text(sql)).scalar()


def _first_sample(metric, since):
    return (SystemSample.query.filter(SystemSample.metric == metric, SystemSample.ts >= since)
            .order_by(SystemSample.ts).first())


def tiles(now=None):
    """Size and its growth, connections and today's peak, cache hit rate, the last backup."""
    now = now or datetime.utcnow()
    size = _scalar('SELECT pg_database_size(current_database())')
    first = _first_sample('db_size', now - GROWTH_WINDOW)
    growth = None
    if first is not None:
        days = max((now - first.ts).days, 1)
        change = size - first.value
        growth = f"{'+' if change >= 0 else '−'}{fmt.size(abs(change))} in {days} day{'' if days == 1 else 's'}"

    used, most = health.connections()
    peak = (db.session.query(func.max(SystemSample.value))
            .filter(SystemSample.metric == 'db_connections', SystemSample.ts >= health.dubai_midnight(now))
            .scalar())
    hit, read = db.session.execute(text(
        'SELECT blks_hit, blks_read FROM pg_stat_database WHERE datname = current_database()')).one()
    cache = round(100 * hit / (hit + read), 1) if hit + read else None

    backup = health.latest_runs().get('backup')
    last_backup = None
    if backup is not None:
        last_backup = {'time': fmt.clock(backup.finished_at), 'ago': fmt.ago(backup.finished_at, now),
                       'size': fmt.size((backup.details or {}).get('size')), 'result': backup.result,
                       'state': health.RED if backup.result == 'failed' else
                       health.AMBER if now - backup.finished_at > health.BACKUP_MAX_AGE else health.GREEN}
    return {
        'size': fmt.size(size), 'growth': growth,
        'connections': used, 'max_connections': most, 'connections_pct': round(100 * used / most),
        'connections_state': health.AMBER if used >= health.CONNECTIONS_WARN_SHARE * most else health.GREEN,
        'peak_today': max(int(peak or 0), used),
        'cache_pct': cache,
        'cache_state': health.GREY if cache is None else health.AMBER if cache < CACHE_WARN_PCT else health.GREEN,
        'shared_buffers': _scalar('SHOW shared_buffers'),
        'backup': last_backup,
    }


def size_history(now=None):
    """[(moment, bytes)]: the database size at the end of each Dubai day, 30 days."""
    now = now or datetime.utcnow()
    day = func.date_trunc('day', SystemSample.ts + fmt.DUBAI.utcoffset(None))
    rows = (db.session.query(day, func.max(SystemSample.value))
            .filter(SystemSample.metric == 'db_size', SystemSample.ts >= now - GROWTH_WINDOW)
            .group_by(day).order_by(day).all())
    return [(start - fmt.DUBAI.utcoffset(None) + timedelta(hours=12), value) for start, value in rows]


def largest_tables(limit=TABLES_SHOWN):
    """[{name, bytes, size}] biggest first, indexes and TOAST included."""
    rows = db.session.execute(text(
        'SELECT relname, pg_total_relation_size(relid) AS bytes FROM pg_stat_user_tables '
        'ORDER BY bytes DESC, relname LIMIT :limit'), {'limit': limit}).all()
    return [{'name': name, 'bytes': size, 'size': fmt.size(size)} for name, size in rows]


def queries(now=None):
    """The slowest queries of the last 24 hours, formatted, or {'enabled': False}."""
    now = now or datetime.utcnow()
    found = slow_queries.slowest(now)
    if not found['enabled']:
        return found
    since = found['since']
    if since is None:
        label = 'since stats reset'
    elif now - since >= slow_queries.WINDOW:
        label = '24h'
    else:
        label = f'since {fmt.clock(since)}'
    rows = [{'text': row['text'], 'mean': fmt.ms(row['mean_ms']), 'calls': row['calls'],
             'total': fmt.ms(row['total_ms'])} for row in found['rows']]
    return {'enabled': True, 'window': label, 'rows': rows}


def maintenance(snapshot, now=None):
    """Pending migrations, the last VACUUM ANALYZE, the most dead rows, the
    restore test, transactions left open, the Postgres version."""
    now = now or datetime.utcnow()
    runs = health.latest_runs()
    vacuum, restore = runs.get('vacuum-analyze'), runs.get('restore-test')

    dead = db.session.execute(text(
        'SELECT relname, n_dead_tup, n_live_tup FROM pg_stat_user_tables '
        'ORDER BY n_dead_tup DESC, relname LIMIT 1')).first()
    dead_row = None
    if dead is not None and dead.n_dead_tup:
        pct = round(100 * dead.n_dead_tup / (dead.n_dead_tup + dead.n_live_tup), 1)
        dead_row = {'table': dead.relname, 'pct': pct,
                    'state': health.AMBER if pct >= DEAD_WARN_PCT else health.GREEN}

    restore_row = None
    if restore is not None:
        restore_row = {'ago': fmt.ago(restore.finished_at, now),
                       'state': health.RED if restore.result == 'failed' else
                       health.AMBER if now - restore.finished_at > health.RESTORE_MAX_AGE else health.GREEN}
    _, most = health.connections()
    return {
        'pending_migrations': (snapshot.get('db') or {}).get('pending_migrations'),
        'vacuum': None if vacuum is None else {'when': fmt.day_time(vacuum.finished_at, now),
                                               'failed': vacuum.result == 'failed'},
        'dead': dead_row,
        'restore': restore_row,
        'idle_in_transaction': _scalar(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
            "AND state LIKE 'idle in transaction%'"),
        'version': _scalar('SHOW server_version').split()[0],
        'max_connections': most,
    }
