"""Weekly restore test (ovp-restore-test.timer, Sundays 04:00): restores the newest
backup into a throwaway ovp_restore_check database as the ovp_restore role, runs
fixed checks against the live database, then drops it. Never touches production."""
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

import psycopg2

from config import Config
from app.modules.system.lib import checks
from app.modules.system.lib.nas_access import nas_app
from app.modules.system.services.jobs import job_run

RESTORE_DB = 'ovp_restore_check'
# Tables a usable backup must hold, and how much of today's live data it must have.
KEY_TABLES = ('users', 'projects', 'deliverables', 'project_files', 'client_servicing', 'activity_logs')
MIN_SHARE = 0.95
MAX_DUMP_AGE = timedelta(days=8)


def with_database(url, name):
    """`url` pointing at database `name`."""
    return urlunparse(urlparse(url)._replace(path=f'/{name}'))


def newest_backup(cur):
    """(finished_at, details) of the newest backup run that left a dump, or None."""
    cur.execute("SELECT finished_at, details FROM job_runs WHERE job = 'backup' "
                "AND details IS NOT NULL ORDER BY started_at DESC LIMIT 1")
    return cur.fetchone()


def fetch_dump(details, scratch):
    """(path, source): the NAS copy downloaded to `scratch` when there is one,
    else the local copy. Raises RuntimeError when neither can be had."""
    if details.get('nas_ok'):
        try:
            from app.modules.core.shared.services import nas
            with nas_app():
                data = nas.download_app_file(details['nas_path'])
            with open(scratch, 'wb') as f:
                f.write(data)
            return scratch, 'nas'
        except Exception:
            pass  # fall back to the local copy below
    local = details.get('local_path')
    if local and os.path.exists(local):
        return local, 'local'
    raise RuntimeError('no dump to restore: the NAS copy and the local copy are both missing')


def count_rows(cur, tables):
    """{table: rows}; a missing table is None. Names come from KEY_TABLES only."""
    counts = {}
    for table in tables:
        cur.execute('SELECT to_regclass(%s)', (table,))
        if cur.fetchone()[0] is None:
            counts[table] = None
            continue
        cur.execute(f'SELECT count(*) FROM {table}')
        counts[table] = cur.fetchone()[0]
    return counts


def problems_with(restored, live, restored_migrations, expected_migrations, dump_age):
    """What is wrong with the restore, as short sentences; empty means it passed."""
    found = []
    for table, live_rows in live.items():
        rows = restored.get(table)
        if rows is None:
            found.append(f'{table} missing')
        elif live_rows and rows < MIN_SHARE * live_rows:
            found.append(f'{table} has {rows} of {live_rows} live rows')
    missing = sorted(set(expected_migrations) - set(restored_migrations))
    if missing:
        found.append(f'{len(missing)} migrations missing: {", ".join(missing[:3])}')
    if dump_age > MAX_DUMP_AGE:
        found.append(f'newest dump is {dump_age.days} days old')
    return found


def _migrations(cur, before=None):
    if before is None:
        cur.execute('SELECT filename FROM schema_migrations')
    else:
        # applied_at has a time zone; ours is naive UTC, so say so.
        cur.execute('SELECT filename FROM schema_migrations WHERE applied_at <= %s',
                    (before.replace(tzinfo=timezone.utc),))
    return [row[0] for row in cur.fetchall()]


def _admin_sql(statement):
    conn = psycopg2.connect(with_database(Config.RESTORE_DATABASE_URL, 'postgres'))
    try:
        conn.autocommit = True  # CREATE/DROP DATABASE can't run in a transaction
        with conn.cursor() as cur:
            cur.execute(statement)
    finally:
        conn.close()


def main():
    with job_run('restore-test') as run:
        if not Config.RESTORE_DATABASE_URL:
            raise RuntimeError('RESTORE_DATABASE_URL is not set')
        live = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
        scratch = os.path.join(Config.BACKUP_DIR, 'restore-check.dump')
        try:
            with live.cursor() as cur:
                newest = newest_backup(cur)
                if newest is None:
                    raise RuntimeError('no backup recorded yet')
                dumped_at, details = newest
                path, source = fetch_dump(details, scratch)
                live_counts = count_rows(cur, KEY_TABLES)
                expected = _migrations(cur, before=dumped_at)

            _admin_sql(f'DROP DATABASE IF EXISTS {RESTORE_DB}')
            _admin_sql(f'CREATE DATABASE {RESTORE_DB}')
            try:
                code, errors = checks.run_status(
                    ('pg_restore', '--no-owner', '--no-privileges', '--dbname',
                     with_database(Config.RESTORE_DATABASE_URL, RESTORE_DB), path), timeout=3600)
                restored = psycopg2.connect(with_database(Config.RESTORE_DATABASE_URL, RESTORE_DB))
                try:
                    with restored.cursor() as cur:
                        restored_counts = count_rows(cur, KEY_TABLES)
                        restored_migrations = _migrations(cur)
                finally:
                    restored.close()
            finally:
                _admin_sql(f'DROP DATABASE IF EXISTS {RESTORE_DB}')
        finally:
            live.close()
            if os.path.exists(scratch):
                os.remove(scratch)

        problems = problems_with(restored_counts, live_counts, restored_migrations, expected,
                                 datetime.utcnow() - dumped_at)
        run.details = {'source': source, 'dump': details.get('nas_path') if source == 'nas' else path,
                       'dumped_at': dumped_at.isoformat(timespec='seconds'),
                       'counts': {t: [restored_counts[t], live_counts[t]] for t in KEY_TABLES},
                       'pg_restore_exit': code, 'pg_restore_notes': errors[-500:] or None,
                       'problems': problems}
        if problems:
            raise RuntimeError('; '.join(problems))
        run.message = f'Restored from {source} copy · {len(KEY_TABLES)} tables checked'
    return 0


if __name__ == '__main__':
    sys.exit(main())
