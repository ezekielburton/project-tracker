"""The job log. Every scheduled job runs inside job_run('<name>'), which saves
the run to job_runs. Jobs are standalone scripts, so this opens its own
connection instead of needing the Flask app."""
import sys
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import psycopg2

from config import Config

RESULT_OK = 'ok'
RESULT_FAILED = 'failed'
MESSAGE_LIMIT = 2000

_INSERT_RUN = (
    'INSERT INTO job_runs (job, started_at, finished_at, result, message, bytes_reclaimed, run_by_id) '
    'VALUES (%s, %s, %s, %s, %s, %s, %s)'
)


def insert_run(cur, job, started, finished, result, message=None, bytes_reclaimed=None, run_by_id=None):
    """Write one job_runs row with `cur`; the caller commits."""
    cur.execute(_INSERT_RUN, (job, started, finished, result,
                              message[:MESSAGE_LIMIT] if message else None,
                              bytes_reclaimed, run_by_id))


def record_run(job, started, finished, result, message=None, bytes_reclaimed=None, run_by_id=None):
    """Save one run of `job` in its own short transaction."""
    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    try:
        with conn, conn.cursor() as cur:
            insert_run(cur, job, started, finished, result, message, bytes_reclaimed, run_by_id)
    finally:
        conn.close()


def _record_safely(*args):
    # A database outage must not change how the job itself ends.
    try:
        record_run(*args)
    except Exception as e:
        print(f'job_runs: could not record {args[0]!r}: {e}', file=sys.stderr)


@contextmanager
def job_run(job, run_by_id=None):
    """Time the block and save it: ok when it finishes, failed with the error when
    it raises (re-raised, so the unit fails too). sys.exit(0) counts as ok.
    Set run.message or run.bytes_reclaimed inside the block."""
    run = SimpleNamespace(message=None, bytes_reclaimed=None)
    started = datetime.utcnow()
    try:
        yield run
    except SystemExit as e:
        failed = e.code not in (0, None)
        _record_safely(job, started, datetime.utcnow(), RESULT_FAILED if failed else RESULT_OK,
                       run.message or (str(e.code) if failed else None), run.bytes_reclaimed, run_by_id)
        raise
    except BaseException as e:
        _record_safely(job, started, datetime.utcnow(), RESULT_FAILED,
                       f'{type(e).__name__}: {e}', run.bytes_reclaimed, run_by_id)
        raise
    _record_safely(job, started, datetime.utcnow(), RESULT_OK, run.message, run.bytes_reclaimed, run_by_id)
