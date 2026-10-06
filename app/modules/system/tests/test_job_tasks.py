"""What each scheduled job does: the backup's paths, pruning and NAS-failure
path, the notifications purge, retention, and the orphaned-uploads report."""
import os
import time
from datetime import datetime, timedelta

import pytest

from app.modules.core.shared.models import Notification, User
from app.modules.system.jobs import backup, orphan_uploads, purge_notifications, retention
from app.modules.system.models import RequestMetric
from app.modules.system.services import jobs

NOW = datetime(2026, 10, 6, 12, 0, 0)


def test_the_nas_keeps_the_old_folder_layout():
    local = datetime(2026, 10, 6, 23, 0, tzinfo=backup.DUBAI)
    assert backup.nas_location(local) == ('/Admin/Database/2026/Week 41', 'Tuesday 06 October Backup.dump')


def test_a_weekly_copy_only_on_sundays(tmp_path):
    tuesday = datetime(2026, 10, 6, 23, 0, tzinfo=backup.DUBAI)
    sunday = datetime(2026, 10, 11, 23, 0, tzinfo=backup.DUBAI)
    assert backup.local_paths(str(tmp_path), tuesday)[1] is None
    nightly, weekly = backup.local_paths(str(tmp_path), sunday)
    assert nightly.endswith(os.path.join('nightly', '2026-10-11.dump'))
    assert weekly.endswith(os.path.join('weekly', '2026-W41.dump'))


def test_prune_keeps_the_newest(tmp_path):
    for day in range(1, 17):
        (tmp_path / f'2026-09-{day:02d}.dump').write_bytes(b'x' * 10)
    assert backup.prune(str(tmp_path), 14) == 20
    assert sorted(os.listdir(tmp_path))[0] == '2026-09-03.dump'
    assert len(os.listdir(tmp_path)) == 14
    assert backup.prune(str(tmp_path / 'missing'), 14) == 0


def _fake_dump(command, timeout):
    path = command[command.index('--file') + 1]
    with open(path, 'wb') as f:
        f.write(b'x' * 10)


def test_a_nas_failure_keeps_the_local_copy_and_fails_the_run(tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(jobs, 'record_run', lambda *args: recorded.append(args))
    monkeypatch.setattr(backup.Config, 'BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(backup.checks, 'run_or_raise', _fake_dump)

    def nas_down(*args):
        raise RuntimeError('NAS unreachable')
    monkeypatch.setattr(backup, 'upload', nas_down)

    with pytest.raises(RuntimeError):
        backup.main()
    job, _, _, result, message, _, _, details = recorded[0]
    assert (job, result) == ('backup', 'failed')
    assert 'NAS unreachable' in message
    assert details['nas_ok'] is False and details['size'] == 10
    assert os.path.exists(details['local_path'])


def test_a_good_backup_records_its_size_and_both_copies(tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(jobs, 'record_run', lambda *args: recorded.append(args))
    monkeypatch.setattr(backup.Config, 'BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(backup.checks, 'run_or_raise', _fake_dump)
    monkeypatch.setattr(backup, 'upload', lambda *args: None)

    backup.main()
    details = recorded[0][7]
    assert recorded[0][3] == 'ok'
    assert details['nas_ok'] is True and details['nas_path'].startswith('/Admin/Database/')


def _user(db_session):
    user = User(name='Purge Test', email='purge-test@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_notifications_older_than_90_days_go_read_or_not(db_session):
    user = _user(db_session)
    for age, read in ((91, False), (120, True), (10, False)):
        db_session.add(Notification(recipient_id=user.id, message='x', notification_type='test',
                                    is_read=read, created_at=NOW - timedelta(days=age)))
    db_session.flush()
    cur = db_session.connection().connection.cursor()
    assert purge_notifications.purge(cur, NOW) >= 2
    assert Notification.query.filter_by(recipient_id=user.id).count() == 1


def test_retention_trims_request_metrics_past_30_days(db_session):
    for age in (31, 29):
        db_session.add(RequestMetric(ts=NOW - timedelta(days=age), method='GET', route='/x-retention-test',
                                     status=200, duration_ms=1))
    db_session.flush()
    cur = db_session.connection().connection.cursor()
    deleted = retention.trim(cur, NOW)
    assert set(deleted) == {'request_metrics', 'heartbeats', 'job_runs'}
    assert RequestMetric.query.filter_by(route='/x-retention-test').count() == 1


def test_orphans_are_old_unreferenced_files_in_the_top_folder(tmp_path):
    week_ago = time.time() - 8 * 86400
    for name in ('kept.pdf', 'orphan.pdf', 'fresh.pdf'):
        (tmp_path / name).write_bytes(b'x' * 5)
    for name in ('kept.pdf', 'orphan.pdf'):
        os.utime(tmp_path / name, (week_ago, week_ago))
    (tmp_path / 'preview-cache').mkdir()
    found = orphan_uploads.find_orphans(str(tmp_path), {'kept.pdf'}, datetime.utcnow())
    assert [f['name'] for f in found] == ['orphan.pdf']
    assert found[0]['size'] == 5
    assert orphan_uploads.find_orphans(str(tmp_path / 'missing'), set(), datetime.utcnow()) == []
