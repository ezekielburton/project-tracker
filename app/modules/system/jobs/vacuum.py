"""VACUUM ANALYZE (ovp-vacuum-analyze.timer, 03:10): reclaims space from dead
rows and refreshes the query planner's statistics, for every table."""
import sys

import psycopg2

from config import Config
from app.modules.system.services.jobs import job_run


def main():
    with job_run('vacuum-analyze'):
        conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
        try:
            conn.autocommit = True  # VACUUM can't run inside a transaction
            with conn.cursor() as cur:
                cur.execute('VACUUM (ANALYZE)')
        finally:
            conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
