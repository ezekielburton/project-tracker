"""Every minute (ovp-snapshot.timer): read the machine, write snapshot.json and
save new app-log events. NAS space and history refresh every 5 minutes, the
slow checks every 6 hours. No Flask app: config, psycopg2 and psutil."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values

from config import Config
from app.modules.system.lib import app_log, checks, host
from app.modules.system.services.jobs import job_run
from app.modules.system.services.snapshot import parse_time, read_snapshot

NAS_EVERY = timedelta(minutes=5)
SAMPLES_EVERY = timedelta(minutes=5)
SLOW_EVERY = timedelta(hours=6)
# A timer tick lands a little early or late; this keeps "every 5 minutes" from slipping to 6.
_SLACK = timedelta(seconds=30)
LOG_KEEP = timedelta(days=7)
SAMPLES_KEEP = timedelta(days=35)
REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

_INSERT_EVENTS = 'INSERT INTO app_log_events (ts, level, source, signature, message, detail) VALUES %s'
_INSERT_SAMPLES = 'INSERT INTO system_samples (ts, metric, value) VALUES %s'


def iso(moment):
    return moment.isoformat(timespec='seconds')


def due(checked_at, every, now):
    """True when a part last refreshed at `checked_at` needs refreshing again."""
    last = parse_time(checked_at)
    return last is None or now - last >= every - _SLACK


def carried(previous, key, every, now, refresh):
    """The previous snapshot's `key` while it is fresh enough, otherwise refresh()
    stamped with checked_at. A refresh that raises is stored as ok False."""
    old = previous.get(key)
    if isinstance(old, dict) and not due(old.get('checked_at'), every, now):
        return old
    try:
        fresh = dict(refresh(), ok=True)
    except Exception as e:
        fresh = {'ok': False, 'error': str(e)[:200]}
    fresh['checked_at'] = iso(now)
    return fresh


def nas_space():
    """Free and total bytes on the NAS project share, through the NAS API."""
    from flask import Flask
    from app.modules.core.shared.services import nas
    app = Flask('ovp-snapshot')
    app.config.from_object(Config)
    with app.app_context():
        space = nas.share_space(Config.NAS_PROJECT_ROOT)
    if space is None:
        raise RuntimeError('share not found')
    return dict(space, share=Config.NAS_PROJECT_ROOT)


def database_reading(conn):
    """Database size and pending migrations, or ok False when it can't be reached."""
    import migrate
    if conn is None:
        return {'ok': False}
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_database_size(current_database())')
            size = cur.fetchone()[0]
        applied = migrate.get_applied(conn)
    except psycopg2.Error:
        conn.rollback()
        return {'ok': False}
    pending = [name for name in migrate.get_all_scripts() if name not in applied]
    return {'ok': True, 'size': size, 'pending_migrations': len(pending)}


def sample_rows(now, snap, previous_mark):
    """History rows for this run and the network mark the next run measures from."""
    reading = snap['host']
    rows = [(now, 'cpu_pct', reading['cpu_pct']),
            (now, 'mem_pct', round(100 * reading['mem_used'] / reading['mem_total'], 1)),
            (now, 'load1', reading['load'][0])]
    for mount in snap['mounts']:
        rows.append((now, f"disk_used:{mount['mount']}", mount['used']))
    if snap['db'].get('ok'):
        rows.append((now, 'db_size', snap['db']['size']))
    mark = {'sent': reading['net_sent'], 'recv': reading['net_recv']}
    if previous_mark:
        for key in ('sent', 'recv'):
            delta = mark[key] - previous_mark.get(key, 0)
            # Counters restart at zero after a reboot.
            rows.append((now, f'net_{key}', delta if delta >= 0 else mark[key]))
    return rows, mark


def save(cur, events, samples, now):
    """Write log events and samples, and drop what is past keeping; the caller commits."""
    if events:
        execute_values(cur, _INSERT_EVENTS, [
            (e['ts'] or now, e['level'], e['source'], e['signature'], e['message'], e['detail'])
            for e in events])
    cur.execute('DELETE FROM app_log_events WHERE ts < %s', (now - LOG_KEEP,))
    if samples:
        execute_values(cur, _INSERT_SAMPLES, samples)
        cur.execute('DELETE FROM system_samples WHERE ts < %s', (now - SAMPLES_KEEP,))


def write_atomic(path, data):
    """Write JSON to a temp file beside `path`, then swap it in, so a reader
    never sees half a file."""
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=folder, prefix='.snapshot-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, default=str)
        os.replace(temp, path)
    except BaseException:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise


def _read_text(path):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def _restore_text(path, text):
    # Put the journal bookmark back, so events not saved are read again next run.
    if text is None:
        try:
            os.remove(path)
        except OSError:
            pass
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)


def _connect():
    try:
        return psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI, connect_timeout=5)
    except psycopg2.Error:
        return None


def collect(now, previous, conn):
    """This run's snapshot: quick readings every time, slower parts carried until due."""
    return {
        'taken_at': iso(now),
        'host': host.host_reading(),
        'mounts': host.mounts(),
        'workers': host.gunicorn_workers(),
        'app': checks.app_version(REPO_DIR),
        'db': database_reading(conn),
        'nas': carried(previous, 'nas', NAS_EVERY, now, nas_space),
        'slow': carried(previous, 'slow', SLOW_EVERY, now, lambda: checks.slow_checks(
            REPO_DIR, Config.LAN_CERT_PATH, Config.PUBLIC_HOSTNAME)),
    }


def main():
    path = Config.SYSTEM_SNAPSHOT_PATH
    cursor_file = os.path.join(os.path.dirname(path), 'journal.cursor')
    with job_run('snapshot') as run:
        now = datetime.utcnow()
        previous = read_snapshot(path)
        conn = _connect()
        try:
            snap = collect(now, previous, conn)
            samples = []
            if due(previous.get('samples_at'), SAMPLES_EVERY, now):
                samples, snap['net_mark'] = sample_rows(now, snap, previous.get('net_mark'))
                snap['samples_at'] = iso(now)

            bookmark = _read_text(cursor_file)
            output = checks.run(checks.journal_command(cursor_file), timeout=60)
            events = app_log.read_events((output or '').splitlines())

            failure = None
            if conn is not None:
                try:
                    with conn, conn.cursor() as cur:
                        save(cur, events, samples, now)
                except psycopg2.Error as e:
                    failure = e
            if conn is None or failure is not None:
                # Nothing was saved: read these log lines and take these samples again next run.
                _restore_text(cursor_file, bookmark)
                snap['samples_at'] = previous.get('samples_at')
                snap['net_mark'] = previous.get('net_mark')
            else:
                snap.setdefault('samples_at', previous.get('samples_at'))
                snap.setdefault('net_mark', previous.get('net_mark'))
            # Written even when the database is down: that is when the page needs it most.
            write_atomic(path, snap)
            run.message = f'{len(events)} log events' if events else None
            if failure is not None:
                raise failure
        finally:
            if conn is not None:
                conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
