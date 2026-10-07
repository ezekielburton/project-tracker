"""The Run now hand-off: a trigger file per job holding who asked, taken by the
job's own run so it is recorded once."""
import pytest

from app.modules.system.services import jobs, run_now


def test_a_request_is_claimed_once(tmp_path):
    run_now.request_run('backup', 7, folder=str(tmp_path))
    assert run_now.pending(folder=str(tmp_path)) == ['backup']
    assert run_now.claim('backup', folder=str(tmp_path)) == 7
    assert run_now.claim('backup', folder=str(tmp_path)) is None
    assert run_now.pending(folder=str(tmp_path)) == []


@pytest.mark.parametrize('job_key', ['heartbeat', 'no-such-job'])
def test_jobs_that_must_not_run_by_hand_are_refused(tmp_path, job_key):
    with pytest.raises(run_now.NotRunnable):
        run_now.request_run(job_key, 7, folder=str(tmp_path))
    assert run_now.pending(folder=str(tmp_path)) == []


def test_a_job_run_takes_the_request_and_records_who(tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(jobs, 'record_run', lambda *args: recorded.append(args))
    monkeypatch.setattr(run_now.Config, 'RUN_NOW_DIR', str(tmp_path))
    run_now.request_run('retention', 42)

    with jobs.job_run('retention'):
        pass
    assert recorded[0][6] == 42
    assert run_now.pending() == []


def test_a_timer_run_has_no_one_behind_it(tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(jobs, 'record_run', lambda *args: recorded.append(args))
    monkeypatch.setattr(run_now.Config, 'RUN_NOW_DIR', str(tmp_path))
    with jobs.job_run('retention'):
        pass
    assert recorded[0][6] is None
