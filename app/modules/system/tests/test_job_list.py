"""The job list and deploy/systemd/ agree: every job has a service and timer
with the same schedule and command, a Run now path unit exactly when it may run
by hand, no unit is unlisted, and each job's script records under its own name."""
import re
from pathlib import Path

import pytest

from app.modules.system.lib.job_list import JOBS

REPO = Path(__file__).resolve().parents[4]
UNITS = REPO / 'deploy' / 'systemd'
SERVER_REPO = '/home/helixadmin/project-tracker'
# Config.RUN_NOW_DIR's default on the server; the path units watch inside it.
SERVER_RUN_NOW_DIR = '/var/lib/ovp/run-now'


def _fields(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)


@pytest.mark.parametrize('job', JOBS, ids=lambda j: j.key)
def test_each_job_has_a_matching_service_and_timer(job):
    timer = _fields(UNITS / f'{job.unit}.timer')
    service = _fields(UNITS / f'{job.unit}.service')
    assert timer['OnCalendar'] == job.on_calendar, f'Change {job.unit}.timer or job_list.py so they agree.'
    assert service['ExecStart'] == f'{SERVER_REPO}/venv/bin/python {job.command}'
    assert service['User'] == 'helixadmin' and service['Type'] == 'oneshot'


@pytest.mark.parametrize('job', JOBS, ids=lambda j: j.key)
def test_a_run_now_path_unit_exactly_for_jobs_that_may_run_by_hand(job):
    path_unit = UNITS / f'{job.unit}.path'
    assert path_unit.exists() == job.run_now
    if job.run_now:
        assert _fields(path_unit)['PathExists'] == f'{SERVER_RUN_NOW_DIR}/{job.key}'


def test_no_unit_file_is_missing_from_the_list():
    listed = {job.unit for job in JOBS}
    on_disk = {path.stem for pattern in ('*.service', '*.timer', '*.path') for path in UNITS.glob(pattern)}
    assert on_disk <= listed, f'Add these to job_list.py or delete them: {sorted(on_disk - listed)}'


@pytest.mark.parametrize('job', JOBS, ids=lambda j: j.key)
def test_each_job_records_under_its_own_name(job):
    if job.command.startswith('-m '):
        script = REPO / (job.command[3:].replace('.', '/') + '.py')
    else:
        script = REPO / job.command
    assert script.exists(), f'{job.command} does not exist'
    if job.key != 'heartbeat':  # the heartbeat's own table is its record
        assert re.search(rf"job_run\('{re.escape(job.key)}'", script.read_text(encoding='utf-8'))
