"""What the admin Overview and System pages read: the status strip's colours,
every Needs attention rule, the two badges, usage with its exclusions, the
next jobs, and "No data" when nothing has been collected."""
from datetime import datetime, timedelta

from app.modules.core.shared.models import PendingNasUpload, User
from app.modules.system.models import (AppLogEvent, DeployRun, Heartbeat, JobRun, RequestMetric,
                                       SystemSample, WorkerStat)
from app.modules.system.services import health

NOW = datetime(2026, 10, 6, 10, 0, 0)  # 14:00 in Dubai, a Tuesday
GB = 1024 ** 3
TB = 1024 ** 4


def _strip(snapshot):
    return {tile['key']: tile for tile in health.status_strip(snapshot, NOW)}


def _run(db_session, job, result='ok', hours_ago=1):
    finished = NOW - timedelta(hours=hours_ago)
    db_session.add(JobRun(job=job, started_at=finished - timedelta(seconds=30), finished_at=finished,
                          result=result))
    db_session.flush()


def _event(db_session, signature, hours_ago=1, level='error', message='boom'):
    db_session.add(AppLogEvent(ts=NOW - timedelta(hours=hours_ago), level=level, source='app',
                               signature=signature, message=message))
    db_session.flush()


def _user(db_session, tag, **fields):
    user = User(name=f'Health {tag}', email=f'health-{tag}@example.com', **fields)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _metric(db_session, user, minutes_ago, method='POST', status=200, route='/projects/<int:id>/save',
            blueprint='projects'):
    db_session.add(RequestMetric(ts=NOW - timedelta(minutes=minutes_ago), method=method, route=route,
                                 blueprint=blueprint, status=status, duration_ms=10, user_id=user.id))
    db_session.flush()


def _epoch(moment):
    return (moment - datetime(1970, 1, 1)).total_seconds()


# ── Nothing collected yet ────────────────────────────────────────────────

def test_with_nothing_collected_the_strip_reads_no_data(db_session):
    strip = _strip({})
    assert [strip[key]['state'] for key in ('app', 'nas', 'sse', 'backup', 'deploy')] == ['grey'] * 5
    assert strip['database']['state'] == 'green'
    assert health.needs_attention({}, NOW) == []
    assert health.headline({}, [], NOW) == {'state': 'grey', 'text': 'no snapshot yet'}


def test_with_nothing_collected_the_system_page_has_empty_parts(db_session):
    view = health.system_view({}, NOW)
    assert view['tiles'] is None and view['storage'] == [] and view['updates'] is None
    assert view['network'] == {'sent': [], 'recv': []}
    assert view['application']['version'] is None


# ── Status strip ─────────────────────────────────────────────────────────

def test_the_app_is_up_with_workers_and_amber_when_one_is_missing(db_session):
    db_session.add(Heartbeat(ts=NOW - timedelta(seconds=40), ok=True, ms=12))
    db_session.flush()
    workers = {'alive': 8, 'total': 9, 'started_at': _epoch(NOW - timedelta(days=42, hours=3))}
    tile = _strip({'workers': workers})['app']
    assert (tile['state'], tile['value'], tile['sub']) == ('amber', 'Up · 42d', 'gunicorn 8/9 workers')


def test_a_failed_heartbeat_is_red(db_session):
    db_session.add(Heartbeat(ts=NOW - timedelta(seconds=40), ok=False, ms=5000))
    db_session.flush()
    assert _strip({})['app']['state'] == 'red'


def test_the_nas_tile_follows_the_snapshot(db_session):
    up = _strip({'nas': {'ok': True, 'free': 8 * TB, 'total': 12 * TB}})['nas']
    assert (up['state'], up['sub']) == ('green', '4.0 TB / 12.0 TB')
    assert _strip({'nas': {'ok': False}})['nas']['state'] == 'red'


def test_open_streams_count_only_live_workers(db_session):
    db_session.add_all([WorkerStat(pid=990_101, sse_open=7, updated_at=NOW - timedelta(seconds=5)),
                        WorkerStat(pid=990_102, sse_open=4, updated_at=NOW - timedelta(minutes=5))])
    db_session.flush()
    _event(db_session, 'sse_relay: SSE relay: LISTEN connection dropped (…), reconnecting in #s.',
           level='warning')
    tile = _strip({})['sse']
    assert (tile['value'], tile['sub']) == ('7 open', '1 reconnect today')


def test_a_recent_backup_and_restore_test_are_green(db_session):
    _run(db_session, 'backup', hours_ago=15)
    _run(db_session, 'restore-test', hours_ago=48)
    assert _strip({})['backup']['state'] == 'green'


def test_an_old_restore_test_makes_the_backup_amber(db_session):
    _run(db_session, 'backup', hours_ago=15)
    _run(db_session, 'restore-test', hours_ago=24 * 9)
    assert _strip({})['backup']['state'] == 'amber'


def test_a_failed_backup_is_red(db_session):
    _run(db_session, 'backup', result='failed', hours_ago=15)
    assert _strip({})['backup']['state'] == 'red'


def test_the_deploy_tile_shows_the_version_and_pending_migrations(db_session):
    db_session.add(DeployRun(ran_at=NOW - timedelta(days=3), tag='v2.6.4', commit_sha='a3f19c2',
                             migrations_applied=2, duration_ms=48000, ok=True))
    db_session.flush()
    tile = _strip({'app': {'version': 'v2.7'}, 'db': {'pending_migrations': 0}})['deploy']
    assert (tile['state'], tile['value'], tile['sub']) == ('grey', 'v2.7', '3 days ago · 0 pending')
    assert _strip({'app': {'version': 'v2.7'}, 'db': {'pending_migrations': 1}})['deploy']['state'] == 'amber'


# ── Needs attention ──────────────────────────────────────────────────────

def test_error_groups_and_failed_jobs_come_first_in_red(db_session):
    _event(db_session, 'IntegrityError · app/x.py · upload', hours_ago=2, message='Exception on /x [POST]')
    _event(db_session, 'IntegrityError · app/x.py · upload', hours_ago=1, message='Exception on /x [POST]')
    _event(db_session, 'old · error', hours_ago=30)
    _run(db_session, 'vacuum-analyze', result='failed')
    items = health.needs_attention({'slow': {'os_security': 3, 'checked_at': NOW.isoformat()}}, NOW)
    assert [item['severity'] for item in items] == ['red', 'red', 'amber']
    assert items[0]['meta'] == '2 in 24h' and items[0]['page'] == 'errors'
    assert items[1]['text'] == 'VACUUM ANALYZE failed'
    assert items[2]['text'] == '3 OS security updates pending'


def test_a_full_disk_says_when_it_will_be_full(db_session):
    db_session.add_all([SystemSample(ts=NOW - timedelta(days=10), metric='disk_used:/var/uploads', value=60 * GB),
                        SystemSample(ts=NOW, metric='disk_used:/var/uploads', value=70 * GB)])
    db_session.flush()
    items = health.needs_attention({'mounts': [{'mount': '/var/uploads', 'used': 70 * GB, 'total': 80 * GB}]}, NOW)
    assert items[0]['text'] == '/var/uploads at 88% · full in about 10 days'


def test_old_backups_stale_snapshots_drift_and_a_stuck_nas_queue(db_session):
    _run(db_session, 'backup', hours_ago=30)
    _run(db_session, 'restore-test', hours_ago=24 * 9)
    db_session.add(PendingNasUpload(nas_path='/Projects/x-health-test.pdf', local_name='x.bin',
                                    created_at=NOW - timedelta(hours=1), updated_at=NOW - timedelta(hours=1)))
    db_session.flush()
    snapshot = {'taken_at': (NOW - timedelta(minutes=20)).isoformat(),
                'app': {'head': 'aaa'}, 'slow': {'main_commit': 'bbb'}}
    texts = [item['text'] for item in health.needs_attention(snapshot, NOW)]
    assert 'Last backup is over a day old' in texts
    assert 'Restore test overdue' in texts
    assert 'Snapshot has stopped updating' in texts
    assert 'Server is behind origin/main' in texts
    assert any(text.endswith('waiting for the NAS') for text in texts)


def test_all_well_reads_normal(db_session):
    snapshot = {'taken_at': (NOW - timedelta(minutes=2)).isoformat()}
    assert health.needs_attention(snapshot, NOW) == []
    assert health.headline(snapshot, [], NOW) == {'state': 'green', 'text': 'all systems normal · snapshot 2 min ago'}


# ── Badges ───────────────────────────────────────────────────────────────

def test_the_errors_badge_counts_new_error_groups_only(db_session):
    _event(db_session, 'x-new-group', hours_ago=2)
    _event(db_session, 'x-old-group', hours_ago=30)
    _event(db_session, 'x-old-group', hours_ago=1)
    _event(db_session, 'x-warning', hours_ago=1, level='warning')
    assert health.new_error_groups(NOW) == 1


def test_the_jobs_badge_counts_jobs_not_runs(db_session):
    for hours in (1, 2, 3):
        _run(db_session, 'snapshot', result='failed', hours_ago=hours)
    _run(db_session, 'backup', result='failed', hours_ago=24 * 8)
    _run(db_session, 'retention')
    assert health.failed_jobs(NOW) == 1


# ── Usage ────────────────────────────────────────────────────────────────

def test_today_counts_saved_changes_by_people_who_count(app, db_session, monkeypatch):
    monkeypatch.setitem(app.config, 'USAGE_EXCLUDED_EMAILS', 'Health-Tester@example.com')
    designer = _user(db_session, 'designer', department='design')
    cs = _user(db_session, 'cs', department='client_servicing')
    admin = _user(db_session, 'admin', is_admin=True)
    tester = _user(db_session, 'tester', department='design')

    _metric(db_session, designer, 2)                                        # counts, active now
    _metric(db_session, cs, 60)                                             # counts
    _metric(db_session, cs, 61, method='GET')                               # a view, not an action
    _metric(db_session, cs, 62, status=500)                                 # failed, not an action
    _metric(db_session, cs, 63, route='/sidebar/track', blueprint='main')   # housekeeping
    _metric(db_session, cs, 64, route='/login', blueprint='auth')           # logging in
    _metric(db_session, admin, 3)                                           # admins are left out
    _metric(db_session, tester, 4)                                          # excluded test account

    numbers = health.today(NOW)
    assert (numbers['active_now'], numbers['actions_today'], numbers['people_today']) == (1, 2, 2)
    assert len(numbers['weeks']) == 13
    assert numbers['weeks'][-1]['actions'] == 2
    assert numbers['weeks'][-1]['start'].weekday() == 0


# ── Next jobs and the System page ────────────────────────────────────────

def test_next_jobs_are_soonest_first_and_flag_a_failed_last_run(db_session):
    _run(db_session, 'backup', result='failed')
    timers = {'ovp-backup': {'next': '2026-10-06T19:00:00'},
              'ovp-snapshot': {'next': '2026-10-06T10:01:00'},
              'ovp-retention': {'next': None}}
    upcoming = health.next_jobs({'timers': timers})
    assert [(job['key'], job['failed']) for job in upcoming] == [('snapshot', False), ('backup', True)]


def test_the_system_page_from_a_full_snapshot(db_session):
    snapshot = {
        'taken_at': NOW.isoformat(),
        'host': {'boot_at': int(_epoch(NOW - timedelta(days=42, hours=7))),
                 'uptime_s': 42 * 86400 + 7 * 3600, 'cpu_pct': 34.2, 'load': [1.2, 1.0, 0.9],
                 'mem_used': 9.8 * GB, 'mem_total': 16 * GB, 'temp_c': None},
        'mounts': [{'mount': '/', 'used': 38 * GB, 'total': 118 * GB}],
        'nas': {'ok': True, 'free': 8 * TB, 'total': 12 * TB, 'share': '/Projects'},
        'slow': {'os_security': 3, 'os_total': 14, 'pip_outdated': 7, 'pip_total': 41,
                 'main_commit': 'abc', 'checked_at': NOW.isoformat(),
                 'certs': [{'name': 'LAN', 'expires_at': (NOW + timedelta(days=200)).isoformat()},
                           {'name': 'Cloudflare', 'expires_at': None}]},
        'app': {'version': 'v2.7', 'commit': 'abc1234', 'head': 'abc'},
        'db': {'ok': True, 'size': 2.3 * GB, 'pending_migrations': 0},
    }
    view = health.system_view(snapshot, NOW)
    assert (view['tiles']['uptime_days'], view['tiles']['uptime_hours']) == (42, 7)
    assert (view['tiles']['cpu_pct'], view['tiles']['mem_pct'], view['tiles']['temp_c']) == (34, 61, None)
    assert [row['label'] for row in view['storage']] == ['/', 'Synology NAS']
    assert view['updates']['app'] == 'up to date'
    assert view['updates']['certs'] == [{'name': 'LAN', 'days_left': 200}, {'name': 'Cloudflare', 'days_left': None}]
    assert view['application']['db_size'] == '2.3 GB'
    assert view['application']['version'] == 'v2.7'


def test_freshness_reads_the_snapshot_age():
    assert health.freshness({}, NOW) == {'state': 'grey', 'text': 'no snapshot yet'}
    fresh = {'taken_at': (NOW - timedelta(minutes=3)).isoformat()}
    assert health.freshness(fresh, NOW) == {'state': 'green', 'text': 'snapshot 3 min ago'}
    stale = {'taken_at': (NOW - timedelta(minutes=30)).isoformat()}
    assert health.freshness(stale, NOW)['state'] == 'amber'
