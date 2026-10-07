"""What the admin Overview and System pages show, built from the snapshot,
the system tables and two live Postgres readings. Read only; every threshold
is a named constant here."""
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import func, or_, text

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import PendingNasUpload, User
from app.modules.system.lib import fmt
from app.modules.system.lib.actions import ACTION_METHODS, NOT_ACTION_BLUEPRINTS, NOT_ACTION_ROUTES
from app.modules.system.lib.job_list import JOBS
from app.modules.system.models import AppLogEvent, DeployRun, Heartbeat, JobRun, RequestMetric, SystemSample, WorkerStat
from app.modules.system.services.snapshot import STALE_AFTER, parse_time

GREEN, AMBER, RED, GREY = 'green', 'amber', 'red', 'grey'

HEARTBEAT_FRESH = timedelta(minutes=3)
WORKER_FRESH = timedelta(seconds=60)
DISK_WARN_PCT = 80
LOAD_WARN_PCT, LOAD_BAD_PCT = 70, 90
CONNECTIONS_WARN_SHARE = 0.8
BACKUP_MAX_AGE = timedelta(hours=26)
RESTORE_MAX_AGE = timedelta(days=8)
NAS_QUEUE_MAX_AGE = timedelta(minutes=30)
DISK_TREND = timedelta(days=14)
ACTIVE_NOW = timedelta(minutes=5)
ACTIVE_RECENT = timedelta(minutes=15)
WEEKS_SHOWN = 13
ATTENTION_ERRORS_SHOWN = 3
RECENT_ERRORS_SHOWN = 3
NEXT_JOBS_SHOWN = 5
# The relay logs this when its LISTEN connection drops; each one is a reconnect.
RELAY_DROP = 'sse_relay: SSE relay: LISTEN connection dropped%'


# ── Shared readings ──────────────────────────────────────────────────────

def latest_runs():
    """{job: its newest JobRun}."""
    rows = (JobRun.query.distinct(JobRun.job)
            .order_by(JobRun.job, JobRun.started_at.desc()).all())
    return {row.job: row for row in rows}


def _dubai_midnight(now):
    """Today's Dubai midnight as naive UTC."""
    local = fmt.local(now)
    return (local.replace(hour=0, minute=0, second=0, microsecond=0)
            - local.utcoffset()).replace(tzinfo=None)


def _connections():
    """(open, max) connections to this database, read live."""
    used = db.session.execute(text(
        'SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()')).scalar()
    most = int(db.session.execute(text('SHOW max_connections')).scalar())
    return used, most


def excluded_user_ids():
    """Admins and the USAGE_EXCLUDED_EMAILS accounts, left out of usage numbers."""
    emails = [e.strip().lower() for e in current_app.config.get('USAGE_EXCLUDED_EMAILS', '').split(',') if e.strip()]
    conditions = [User.is_admin.is_(True)]
    if emails:
        conditions.append(func.lower(User.email).in_(emails))
    return [row.id for row in User.query.with_entities(User.id).filter(or_(*conditions))]


def _counted(query):
    excluded = excluded_user_ids()
    query = query.filter(RequestMetric.user_id.isnot(None))
    return query.filter(RequestMetric.user_id.notin_(excluded)) if excluded else query


def _actions(query):
    return (query.filter(RequestMetric.method.in_(ACTION_METHODS), RequestMetric.status < 400,
                         or_(RequestMetric.blueprint.is_(None), RequestMetric.blueprint.notin_(NOT_ACTION_BLUEPRINTS)),
                         RequestMetric.route.notin_(NOT_ACTION_ROUTES)))


def _people_since(since):
    return _counted(db.session.query(func.count(func.distinct(RequestMetric.user_id)))
                    .filter(RequestMetric.ts >= since)).scalar() or 0


def _disk_trend(mount, now):
    """Bytes per day the mount grew over DISK_TREND, or None without two samples."""
    rows = (SystemSample.query.filter(SystemSample.metric == f'disk_used:{mount}',
                                      SystemSample.ts >= now - DISK_TREND)
            .order_by(SystemSample.ts).all())
    if len(rows) < 2:
        return None
    days = (rows[-1].ts - rows[0].ts).total_seconds() / 86400
    return (rows[-1].value - rows[0].value) / days if days >= 1 else None


def _pct(used, total):
    return round(100 * used / total) if total else None


def _load_state(pct):
    if pct is None:
        return GREY
    return RED if pct >= LOAD_BAD_PCT else AMBER if pct >= LOAD_WARN_PCT else GREEN


# ── Badges ───────────────────────────────────────────────────────────────

def new_error_groups(now=None):
    """Error signatures first seen in the last 24 hours (the Errors badge)."""
    since = (now or datetime.utcnow()) - timedelta(hours=24)
    groups = (db.session.query(AppLogEvent.signature).filter(AppLogEvent.level == 'error')
              .group_by(AppLogEvent.signature).having(func.min(AppLogEvent.ts) >= since).subquery())
    return db.session.query(func.count()).select_from(groups).scalar() or 0


def failed_jobs(now=None):
    """Jobs with at least one failed run in 7 days (the Jobs badge)."""
    since = (now or datetime.utcnow()) - timedelta(days=7)
    return (db.session.query(func.count(func.distinct(JobRun.job)))
            .filter(JobRun.result == 'failed', JobRun.started_at >= since).scalar() or 0)


# ── Overview ─────────────────────────────────────────────────────────────

def _tile(key, label, state, value, sub=None):
    return {'key': key, 'label': label, 'state': state, 'value': value, 'sub': sub}


def _app_tile(snapshot, now):
    beat = Heartbeat.query.order_by(Heartbeat.ts.desc()).first()
    workers = snapshot.get('workers') or {}
    if beat is None or now - beat.ts > HEARTBEAT_FRESH:
        return _tile('app', 'Application', GREY, 'No data')
    if not beat.ok:
        return _tile('app', 'Application', RED, 'Down', fmt.ago(beat.ts, now))
    sub, state, value = None, GREEN, 'Up'
    if workers:
        sub = f"gunicorn {workers['alive']}/{workers['total']} workers"
        state = AMBER if workers['alive'] < workers['total'] else GREEN
        days = int((now - datetime.utcfromtimestamp(workers['started_at'])).total_seconds() // 86400)
        value = f'Up · {days}d'
    return _tile('app', 'Application', state, value, sub)


def _database_tile():
    used, most = _connections()
    state = AMBER if used >= CONNECTIONS_WARN_SHARE * most else GREEN
    return _tile('database', 'Database', state, 'Connected', f'{used} / {most} connections')


def _nas_tile(snapshot):
    nas = snapshot.get('nas')
    if not nas:
        return _tile('nas', 'NAS', GREY, 'No data')
    if not nas.get('ok'):
        return _tile('nas', 'NAS', RED, 'Unreachable')
    used = nas['total'] - nas['free']
    return _tile('nas', 'NAS', GREEN, 'Reachable', f"{fmt.size(used)} / {fmt.size(nas['total'])}")


def _sse_tile(now):
    open_streams = (db.session.query(func.sum(WorkerStat.sse_open))
                    .filter(WorkerStat.updated_at >= now - WORKER_FRESH).scalar())
    if open_streams is None:
        return _tile('sse', 'SSE relay', GREY, 'No data')
    drops = AppLogEvent.query.filter(AppLogEvent.signature.like(RELAY_DROP),
                                     AppLogEvent.ts >= _dubai_midnight(now)).count()
    return _tile('sse', 'SSE relay', GREEN, f'{open_streams} open',
                 f"{drops} reconnect{'' if drops == 1 else 's'} today")


def _backup_tile(runs, now):
    backup, restore = runs.get('backup'), runs.get('restore-test')
    if backup is None:
        return _tile('backup', 'Backup', GREY, 'No data')
    if backup.result == 'failed':
        state, value = RED, 'Failed'
    else:
        state = AMBER if now - backup.finished_at > BACKUP_MAX_AGE else GREEN
        value = f'Last {fmt.clock(backup.finished_at)}'
    if restore is None:
        sub = 'no restore test yet'
    else:
        sub = f'restore test {fmt.ago(restore.finished_at, now)}'
        if restore.result == 'failed' or now - restore.finished_at > RESTORE_MAX_AGE:
            state = RED if state == RED else AMBER
    return _tile('backup', 'Backup', state, value, sub)


def _behind_main(snapshot):
    main = (snapshot.get('slow') or {}).get('main_commit')
    head = (snapshot.get('app') or {}).get('head')
    return bool(main and head and main != head)


def _deploy_tile(snapshot, now):
    deploy = DeployRun.query.order_by(DeployRun.ran_at.desc()).first()
    pending = (snapshot.get('db') or {}).get('pending_migrations')
    version = (snapshot.get('app') or {}).get('version') or (deploy.tag if deploy else None)
    if version is None:
        return _tile('deploy', 'Deploy', GREY, 'No data')
    parts = [fmt.ago(deploy.ran_at, now)] if deploy else []
    if pending is not None:
        parts.append(f'{pending} pending')
    state = AMBER if pending or _behind_main(snapshot) else GREY
    return _tile('deploy', 'Deploy', state, version, ' · '.join(parts) or None)


def status_strip(snapshot, now=None):
    """The six status tiles: App, Database, NAS, SSE, Backup, Deploy."""
    now = now or datetime.utcnow()
    runs = latest_runs()
    return [_app_tile(snapshot, now), _database_tile(), _nas_tile(snapshot), _sse_tile(now),
            _backup_tile(runs, now), _deploy_tile(snapshot, now)]


def _item(severity, text, meta, page):
    return {'severity': severity, 'text': text, 'meta': meta, 'page': page}


def needs_attention(snapshot, now=None):
    """What needs the admin, red first; empty when all is well."""
    now = now or datetime.utcnow()
    items = []

    since = now - timedelta(hours=24)
    groups = (db.session.query(AppLogEvent.signature, func.count(), func.max(AppLogEvent.ts),
                               func.max(AppLogEvent.message))
              .filter(AppLogEvent.level == 'error', AppLogEvent.ts >= since)
              .group_by(AppLogEvent.signature).order_by(func.max(AppLogEvent.ts).desc()).all())
    for signature, count, last, message in groups[:ATTENTION_ERRORS_SHOWN]:
        items.append(_item(RED, f'{message or signature} · {fmt.clock(last)}', f'{count} in 24h', 'errors'))
    if len(groups) > ATTENTION_ERRORS_SHOWN:
        items.append(_item(RED, f'{len(groups) - ATTENTION_ERRORS_SHOWN} more error groups', '24h', 'errors'))

    runs = latest_runs()
    for job in JOBS:
        run = runs.get(job.key)
        if run is not None and run.result == 'failed':
            items.append(_item(RED, f'{job.label} failed', fmt.ago(run.finished_at, now), 'jobs'))
    backup, restore = runs.get('backup'), runs.get('restore-test')
    if backup is not None and backup.result != 'failed' and now - backup.finished_at > BACKUP_MAX_AGE:
        items.append(_item(AMBER, 'Last backup is over a day old', fmt.ago(backup.finished_at, now), 'jobs'))
    if restore is not None and restore.result != 'failed' and now - restore.finished_at > RESTORE_MAX_AGE:
        items.append(_item(AMBER, 'Restore test overdue', fmt.ago(restore.finished_at, now), 'jobs'))

    taken = parse_time(snapshot.get('taken_at'))
    if taken is not None and now - taken > STALE_AFTER:
        items.append(_item(AMBER, 'Snapshot has stopped updating', fmt.ago(taken, now), 'jobs'))

    for mount in snapshot.get('mounts') or []:
        pct = _pct(mount['used'], mount['total'])
        if pct is not None and pct >= DISK_WARN_PCT:
            growth = _disk_trend(mount['mount'], now)
            text = f"{mount['mount']} at {pct}%"
            if growth and growth > 0:
                text += f" · full in about {int((mount['total'] - mount['used']) / growth)} days"
            items.append(_item(AMBER, text, 'disk', 'system'))

    slow = snapshot.get('slow') or {}
    if slow.get('os_security'):
        count = slow['os_security']
        items.append(_item(AMBER, f"{count} OS security update{'' if count == 1 else 's'} pending",
                           fmt.ago(parse_time(slow.get('checked_at')), now), 'system'))
    if _behind_main(snapshot):
        items.append(_item(AMBER, 'Server is behind origin/main', 'version', 'system'))

    oldest = db.session.query(func.min(PendingNasUpload.created_at)).scalar()
    if oldest is not None and now - oldest > NAS_QUEUE_MAX_AGE:
        queued = PendingNasUpload.query.count()
        items.append(_item(AMBER, f"{queued} file{'' if queued == 1 else 's'} waiting for the NAS",
                           f'since {fmt.ago(oldest, now)}', 'system'))

    return sorted(items, key=lambda item: item['severity'] != RED)


def today(now=None):
    """Active now, actions today, people today and actions per week (13 weeks),
    leaving out admins and the excluded accounts."""
    now = now or datetime.utcnow()
    midnight = _dubai_midnight(now)
    actions_today = _actions(_counted(RequestMetric.query.filter(RequestMetric.ts >= midnight))).count()

    this_week = midnight - timedelta(days=fmt.local(now).weekday())
    first_week = this_week - timedelta(weeks=WEEKS_SHOWN - 1)
    week = func.date_trunc('week', RequestMetric.ts + timedelta(hours=4))
    counts = dict(_actions(_counted(db.session.query(week, func.count())
                                     .filter(RequestMetric.ts >= first_week)))
                  .group_by(week).all())
    weeks = []
    for index in range(WEEKS_SHOWN):
        start = first_week + timedelta(weeks=index)
        local_start = (start + timedelta(hours=4)).replace(hour=0, minute=0, second=0, microsecond=0)
        weeks.append({'start': local_start.date(), 'actions': counts.get(local_start, 0)})
    return {
        'active_now': _people_since(now - ACTIVE_NOW),
        'actions_today': actions_today,
        'people_today': _people_since(midnight),
        'weeks': weeks,
    }


def next_jobs(snapshot, limit=NEXT_JOBS_SHOWN):
    """The next timers to fire, soonest first, with whether the job's last run failed."""
    timers = snapshot.get('timers') or {}
    runs = latest_runs()
    upcoming = []
    for job in JOBS:
        due = parse_time((timers.get(job.unit) or {}).get('next'))
        if due is not None:
            run = runs.get(job.key)
            upcoming.append({'key': job.key, 'label': job.label, 'next': due,
                             'failed': run is not None and run.result == 'failed'})
    return sorted(upcoming, key=lambda job: job['next'])[:limit]


def headline(snapshot, items, now=None):
    """The line beside the page title: whether all is well and how fresh the snapshot is."""
    now = now or datetime.utcnow()
    taken = parse_time(snapshot.get('taken_at'))
    fresh = f'snapshot {fmt.ago(taken, now)}' if taken else 'no snapshot yet'
    if items:
        count = len(items)
        return {'state': AMBER, 'text': f"{count} need{'s' if count == 1 else ''} attention · {fresh}"}
    return {'state': GREEN if taken else GREY, 'text': f'all systems normal · {fresh}' if taken else fresh}


# ── System ───────────────────────────────────────────────────────────────

def freshness(snapshot, now=None):
    """How old the snapshot is, for the System page's header line."""
    now = now or datetime.utcnow()
    taken = parse_time(snapshot.get('taken_at'))
    if taken is None:
        return {'state': GREY, 'text': 'no snapshot yet'}
    return {'state': AMBER if now - taken > STALE_AFTER else GREEN, 'text': f'snapshot {fmt.ago(taken, now)}'}


def host_tiles(snapshot):
    """Uptime, CPU, memory and temperature, or None without a reading."""
    host = snapshot.get('host')
    if not host:
        return None
    mem_pct = _pct(host['mem_used'], host['mem_total'])
    return {
        'uptime_days': host['uptime_s'] // 86400,
        'uptime_hours': host['uptime_s'] % 86400 // 3600,
        'boot': fmt.local(datetime.utcfromtimestamp(host['boot_at'])),
        'cpu_pct': round(host['cpu_pct']), 'cpu_state': _load_state(host['cpu_pct']),
        'load': host['load'],
        'mem_pct': mem_pct, 'mem_state': _load_state(mem_pct),
        'mem_used': fmt.size(host['mem_used']), 'mem_total': fmt.size(host['mem_total']),
        'temp_c': host.get('temp_c'),
    }


def storage(snapshot):
    """One row per mount, then the NAS share."""
    rows = []
    for mount in snapshot.get('mounts') or []:
        pct = _pct(mount['used'], mount['total'])
        rows.append({'label': mount['mount'], 'detail': None, 'used': fmt.size(mount['used']),
                     'total': fmt.size(mount['total']), 'pct': pct,
                     'state': AMBER if pct is not None and pct >= DISK_WARN_PCT else GREEN})
    nas = snapshot.get('nas') or {}
    if nas.get('ok'):
        used = nas['total'] - nas['free']
        pct = _pct(used, nas['total'])
        rows.append({'label': 'Synology NAS', 'detail': nas.get('share'), 'used': fmt.size(used),
                     'total': fmt.size(nas['total']), 'pct': pct,
                     'state': AMBER if pct >= DISK_WARN_PCT else GREEN})
    return rows


def network(now=None):
    """Bytes sent and received per 5-minute sample over the last 24 hours."""
    now = now or datetime.utcnow()
    return {key: [(row.ts, row.value) for row in SystemSample.query
                  .filter(SystemSample.metric == f'net_{key}', SystemSample.ts >= now - timedelta(hours=24))
                  .order_by(SystemSample.ts)]
            for key in ('sent', 'recv')}


def updates(snapshot, now=None):
    """OS and Python updates, the app against origin/main and certificate days left."""
    now = now or datetime.utcnow()
    slow = snapshot.get('slow')
    if not slow or not slow.get('ok', True):
        return None
    certs = []
    for cert in slow.get('certs') or []:
        expires = parse_time(cert.get('expires_at'))
        certs.append({'name': cert['name'], 'days_left': (expires - now).days if expires else None})
    main = slow.get('main_commit')
    return {
        'os_security': slow.get('os_security'), 'os_total': slow.get('os_total'),
        'pip_outdated': slow.get('pip_outdated'), 'pip_total': slow.get('pip_total'),
        'app': None if not main else ('behind' if _behind_main(snapshot) else 'up to date'),
        'certs': certs, 'checked': fmt.clock(parse_time(slow.get('checked_at'))),
    }


def application(snapshot, now=None):
    """Database size and connections, migrations, failures, who is on, the version and recent errors."""
    now = now or datetime.utcnow()
    since = now - timedelta(hours=24)
    used, most = _connections()
    database = snapshot.get('db') or {}
    app = snapshot.get('app') or {}
    return {
        'db_size': fmt.size(database.get('size')),
        'connections': used, 'max_connections': most,
        'pending_migrations': database.get('pending_migrations'),
        'failures_24h': (JobRun.query.filter(JobRun.result == 'failed', JobRun.started_at >= since).count()
                         + AppLogEvent.query.filter(AppLogEvent.ts >= since,
                                                    AppLogEvent.level.in_(('error', 'warning')),
                                                    AppLogEvent.source.like('nas%')).count()),
        'people_15min': _people_since(now - ACTIVE_RECENT),
        'version': app.get('version'), 'commit': app.get('commit'),
        'recent_errors': [{'time': fmt.clock(event.ts), 'level': event.level, 'message': event.message}
                          for event in AppLogEvent.query
                          .filter(AppLogEvent.ts >= since, AppLogEvent.level.in_(('error', 'warning')))
                          .order_by(AppLogEvent.ts.desc()).limit(RECENT_ERRORS_SHOWN)],
    }


def system_view(snapshot, now=None):
    """Everything the System page shows, card by card. A part the snapshot lacks is None."""
    now = now or datetime.utcnow()
    return {'tiles': host_tiles(snapshot), 'storage': storage(snapshot), 'network': network(now),
            'updates': updates(snapshot, now), 'application': application(snapshot, now)}
