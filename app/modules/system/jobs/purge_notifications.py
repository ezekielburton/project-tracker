"""Notifications purge (ovp-notifications-purge.timer, Sundays 04:10): deletes
every notification older than 90 days, read or not."""
import sys
from datetime import datetime, timedelta

import psycopg2

from config import Config
from app.modules.system.services.jobs import job_run

KEEP = timedelta(days=90)


def purge(cur, now):
    """Delete notifications older than KEEP; returns how many went."""
    cur.execute('DELETE FROM notifications WHERE created_at < %s', (now - KEEP,))
    return cur.rowcount


def main():
    with job_run('notifications-purge') as run:
        conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
        try:
            with conn, conn.cursor() as cur:
                deleted = purge(cur, datetime.utcnow())
        finally:
            conn.close()
        run.message = f'{deleted} deleted'
        run.details = {'deleted': deleted}
    return 0


if __name__ == '__main__':
    sys.exit(main())
