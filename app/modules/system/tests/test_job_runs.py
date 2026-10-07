"""job_run saves ok or failed with the right message, never hides how the job
ended, and insert_run writes the row."""
from datetime import datetime

import pytest

from app.modules.system.models import JobRun
from app.modules.system.services import jobs


@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, 'record_run', lambda *args: calls.append(args))
    return calls


def test_a_finished_job_is_recorded_ok_with_its_message(recorded):
    with jobs.job_run('preview-cache-cleanup') as run:
        run.message = 'Removed 4 files'
        run.bytes_reclaimed = 2048
    job, started, finished, result, message, reclaimed, run_by_id, details = recorded[0]
    assert (job, result, message, reclaimed, run_by_id, details) == (
        'preview-cache-cleanup', 'ok', 'Removed 4 files', 2048, None, None)
    assert finished >= started


def test_an_error_is_recorded_failed_and_raised(recorded):
    with pytest.raises(ValueError):
        with jobs.job_run('nightly-backup'):
            raise ValueError('NAS unreachable')
    assert recorded[0][3] == 'failed'
    assert recorded[0][4] == 'ValueError: NAS unreachable'


@pytest.mark.parametrize('code, result', [(0, 'ok'), (None, 'ok'), (1, 'failed')])
def test_sys_exit_is_recorded_by_its_code(recorded, code, result):
    with pytest.raises(SystemExit):
        with jobs.job_run('nightly-backup'):
            raise SystemExit(code)
    assert recorded[0][3] == result


def test_details_are_kept_on_failure_too(recorded):
    with pytest.raises(RuntimeError):
        with jobs.job_run('nightly-backup') as run:
            run.details = {'local_path': '/home/helixadmin/backups/nightly/2026-10-06.dump'}
            raise RuntimeError('NAS unreachable')
    assert recorded[0][7] == {'local_path': '/home/helixadmin/backups/nightly/2026-10-06.dump'}


def test_run_now_records_who_pressed_it(recorded):
    with jobs.job_run('vacuum-analyze', run_by_id=7):
        pass
    assert recorded[0][6] == 7


def test_a_recording_failure_does_not_fail_the_job(monkeypatch, capsys):
    def down(*args):
        raise RuntimeError('database down')
    monkeypatch.setattr(jobs, 'record_run', down)
    with jobs.job_run('preview-cache-cleanup'):
        pass
    assert 'could not record' in capsys.readouterr().err


def test_insert_run_writes_the_row_and_caps_the_message(db_session):
    cur = db_session.connection().connection.cursor()
    now = datetime.utcnow()
    jobs.insert_run(cur, 'x-job-test', now, now, jobs.RESULT_FAILED, 'e' * 5000,
                    details={'files': ['a.pdf']})
    row = JobRun.query.filter_by(job='x-job-test').one()
    assert row.result == 'failed'
    assert len(row.message) == jobs.MESSAGE_LIMIT
    assert row.details == {'files': ['a.pdf']}
