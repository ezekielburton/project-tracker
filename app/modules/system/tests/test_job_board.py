"""What the Jobs page reads: one row per listed job with its last run and next
run, the tiles, and the latest orphaned-uploads report."""
from datetime import datetime, timedelta

from app.modules.system.lib.job_list import JOBS
from app.modules.system.models import Heartbeat, JobRun
from app.modules.system.services import job_board

NOW = datetime(2031, 3, 4, 10, 0, 0)


def _run(db_session, job, hours_ago, result='ok', seconds=4, reclaimed=None, details=None, message=None):
    finished = NOW - timedelta(hours=hours_ago)
    db_session.add(JobRun(job=job, started_at=finished - timedelta(seconds=seconds), finished_at=finished,
                          result=result, bytes_reclaimed=reclaimed, details=details, message=message))
    db_session.flush()


def test_one_row_per_job_with_last_and_next_run(db_session):
    _run(db_session, 'backup', 11, seconds=38)
    _run(db_session, 'restore-test', 24 * 9, result='failed', seconds=130, message='row counts short')
    snapshot = {'timers': {'ovp-backup': {'next': (NOW + timedelta(hours=9)).isoformat()}}}
    rows = {row['key']: row for row in job_board.rows(snapshot, NOW)}
    assert list(rows) == [job.key for job in JOBS]
    assert rows['backup']['last'] == '11 h ago' and rows['backup']['duration'] == '38 s'
    assert rows['backup']['due'] == NOW + timedelta(hours=9) and rows['backup']['run_now']
    assert rows['restore-test']['failed'] and rows['restore-test']['duration'] == '2 m 10 s'
    assert rows['heartbeat']['run_now'] is False and rows['heartbeat']['last'] is None  # no beats yet


def test_the_heartbeat_row_reads_its_last_beat(db_session):
    db_session.add(Heartbeat(ts=NOW - timedelta(seconds=30), ok=False, ms=12))
    db_session.flush()
    row = job_board.rows({}, NOW)[0]
    assert row['key'] == 'heartbeat' and row['last'] == 'just now'
    assert row['duration'] == '12 ms' and row['failed'] and row['result'] == 'failed'


def test_durations():
    assert job_board.duration(0.3) == '0.3 s'
    assert job_board.duration(38) == '38 s'
    assert job_board.duration(130) == '2 m 10 s'


def test_tiles(db_session):
    _run(db_session, 'restore-test', 24 * 2, result='failed')
    _run(db_session, 'restore-test', 24 * 9, result='failed')
    _run(db_session, 'preview-cache-cleanup', 5, reclaimed=3 * 1024 ** 3)
    _run(db_session, 'orphan-uploads', 24 * 40, reclaimed=5 * 1024 ** 3)  # outside 30 days
    snapshot = {'timers': {'ovp-snapshot': {'next': (NOW + timedelta(minutes=1)).isoformat()}}}
    tiles = job_board.tiles(snapshot, NOW)
    assert tiles['scheduled'] == len(JOBS)
    assert tiles['failed'] == 1 and tiles['failed_names'] == ['Weekly restore test']
    assert tiles['next']['key'] == 'snapshot'
    assert tiles['reclaimed'] == 3 * 1024 ** 3


def test_orphans_report(db_session):
    assert job_board.orphans(NOW) is None
    _run(db_session, 'orphan-uploads', 7, details={'count': 2, 'bytes': 3072, 'files': [
        {'name': 'a.pdf', 'size': 2048, 'modified': (NOW - timedelta(days=40)).isoformat()},
        {'name': 'b.png', 'size': 1024, 'modified': (NOW - timedelta(days=50)).isoformat()}]})
    found = job_board.orphans(NOW)
    assert found['count'] == 2 and found['size'] == '3.0 KB' and found['when'] == '7 h ago'
    assert [f['name'] for f in found['files']] == ['a.pdf', 'b.png'] and found['files'][0]['size'] == '2.0 KB'
