"""Data retention (ovp-retention.timer, Sundays 04:15): trims the system
module's own tables to what the admin pages show."""
import sys
from datetime import datetime, timedelta

import psycopg2

from config import Config
from app.modules.system.lib.actions import ACTION_METHODS
from app.modules.system.services.jobs import job_run

# Table -> (timestamp column, how long rows are kept). Fixed names, never from input.
KEEP = {
    'heartbeats': ('ts', timedelta(days=35)),
    'job_runs': ('started_at', timedelta(days=90)),
}
# Page views go after 30 days; saved changes stay 100, for the 13-week actions chart.
VIEWS_KEEP = timedelta(days=30)
WRITES_KEEP = timedelta(days=100)


def trim(cur, now):
    """Delete rows past keeping in each table; returns {table: rows deleted}."""
    cur.execute('DELETE FROM request_metrics WHERE ts < %s AND method NOT IN %s',
                (now - VIEWS_KEEP, ACTION_METHODS))
    views = cur.rowcount
    cur.execute('DELETE FROM request_metrics WHERE ts < %s', (now - WRITES_KEEP,))
    deleted = {'request_metrics': views + cur.rowcount}
    for table, (column, keep) in KEEP.items():
        cur.execute(f'DELETE FROM {table} WHERE {column} < %s', (now - keep,))
        deleted[table] = cur.rowcount
    return deleted


def main():
    with job_run('retention') as run:
        conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
        try:
            with conn, conn.cursor() as cur:
                deleted = trim(cur, datetime.utcnow())
        finally:
            conn.close()
        run.message = f'{sum(deleted.values())} rows deleted'
        run.details = deleted
    return 0


if __name__ == '__main__':
    sys.exit(main())
