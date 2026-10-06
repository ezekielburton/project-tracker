"""The snapshot: the reader never fails, the file is swapped in whole, slower
parts are carried until due, history rows and the saved tables."""
import json
import os
from datetime import datetime, timedelta

from app.modules.system.collectors import snapshot as collector
from app.modules.system.models import AppLogEvent, SystemSample
from app.modules.system.services.snapshot import is_stale, read_snapshot

NOW = datetime(2026, 10, 6, 12, 0, 0)


def test_a_missing_broken_or_odd_file_reads_as_empty(tmp_path):
    assert read_snapshot(str(tmp_path / 'none.json')) == {}
    broken = tmp_path / 'broken.json'
    broken.write_text('{"taken_at": "2026-10-06T1')
    assert read_snapshot(str(broken)) == {}
    listed = tmp_path / 'list.json'
    listed.write_text('[1, 2]')
    assert read_snapshot(str(listed)) == {}


def test_staleness():
    assert is_stale({}, NOW)
    assert not is_stale({'taken_at': (NOW - timedelta(minutes=2)).isoformat()}, NOW)
    assert is_stale({'taken_at': (NOW - timedelta(minutes=16)).isoformat()}, NOW)


def test_the_file_is_swapped_in_whole_and_no_temp_is_left(tmp_path):
    path = str(tmp_path / 'ovp' / 'snapshot.json')
    collector.write_atomic(path, {'taken_at': 'first'})
    collector.write_atomic(path, {'taken_at': 'second'})
    assert read_snapshot(path) == {'taken_at': 'second'}
    assert os.listdir(tmp_path / 'ovp') == ['snapshot.json']


def test_a_part_is_carried_until_due_then_refreshed():
    calls = []

    def refresh():
        calls.append(1)
        return {'free': 5}

    young = {'nas': {'ok': True, 'free': 1, 'checked_at': (NOW - timedelta(minutes=2)).isoformat()}}
    assert collector.carried(young, 'nas', collector.NAS_EVERY, NOW, refresh)['free'] == 1
    old = {'nas': {'ok': True, 'free': 1, 'checked_at': (NOW - timedelta(minutes=5)).isoformat()}}
    fresh = collector.carried(old, 'nas', collector.NAS_EVERY, NOW, refresh)
    assert fresh == {'free': 5, 'ok': True, 'checked_at': NOW.isoformat()}
    assert collector.carried({}, 'nas', collector.NAS_EVERY, NOW, refresh)['ok'] is True
    assert len(calls) == 2


def test_a_failed_refresh_is_stored_as_not_ok():
    def unreachable():
        raise RuntimeError('NAS unreachable')
    part = collector.carried({}, 'nas', collector.NAS_EVERY, NOW, unreachable)
    assert part['ok'] is False and part['error'] == 'NAS unreachable'


def _snap(sent, recv):
    return {
        'host': {'cpu_pct': 12.5, 'mem_used': 4, 'mem_total': 16, 'load': [1.2, 1.0, 0.9],
                 'net_sent': sent, 'net_recv': recv},
        'mounts': [{'mount': '/', 'used': 100, 'total': 200}],
        'db': {'ok': True, 'size': 2048},
    }


def test_history_rows_and_network_deltas():
    rows, mark = collector.sample_rows(NOW, _snap(1500, 900), {'sent': 1000, 'recv': 1000})
    values = {metric: value for _, metric, value in rows}
    assert values['cpu_pct'] == 12.5 and values['mem_pct'] == 25.0
    assert values['disk_used:/'] == 100 and values['db_size'] == 2048
    assert values['net_sent'] == 500
    assert values['net_recv'] == 900  # counter restarted after a reboot
    assert mark == {'sent': 1500, 'recv': 900}


def test_the_first_sample_has_no_network_delta():
    rows, _ = collector.sample_rows(NOW, _snap(1500, 900), None)
    assert not any(metric.startswith('net_') for _, metric, _ in rows)


def test_collect_reads_quick_parts_and_carries_slow_ones(monkeypatch):
    monkeypatch.setattr(collector.host, 'host_reading', lambda: {'cpu_pct': 1})
    monkeypatch.setattr(collector.host, 'mounts', lambda: [])
    monkeypatch.setattr(collector.host, 'gunicorn_workers', lambda: None)
    monkeypatch.setattr(collector.checks, 'app_version', lambda repo: {'version': 'v2.7'})
    monkeypatch.setattr(collector.checks, 'timer_states', lambda units: {'ovp-backup': {'last': None, 'next': None}})

    def not_now():
        raise AssertionError('should be carried')
    monkeypatch.setattr(collector.checks, 'slow_checks', lambda *a: not_now())
    monkeypatch.setattr(collector, 'nas_space', not_now)
    recent = (NOW - timedelta(minutes=1)).isoformat()
    previous = {'nas': {'ok': True, 'checked_at': recent}, 'slow': {'ok': True, 'checked_at': recent}}

    snap = collector.collect(NOW, previous, None)
    assert snap['taken_at'] == NOW.isoformat()
    assert snap['db'] == {'ok': False}
    assert snap['timers'] == {'ovp-backup': {'last': None, 'next': None}}
    assert snap['nas'] is previous['nas'] and snap['slow'] is previous['slow']
    json.dumps(snap)


def test_save_writes_events_and_samples_and_drops_old_ones(db_session):
    cur = db_session.connection().connection.cursor()
    old = NOW - timedelta(days=40)
    collector.save(cur, [{'ts': old, 'level': 'error', 'source': 'x', 'signature': 'x-old-test',
                          'message': 'm', 'detail': None}], [(old, 'x_old_metric', 1.0)], old)
    collector.save(cur, [{'ts': NOW, 'level': 'error', 'source': 'x', 'signature': 'x-new-test',
                          'message': 'm', 'detail': 'd'}], [(NOW, 'x_new_metric', 2.0)], NOW)
    assert AppLogEvent.query.filter_by(signature='x-old-test').count() == 0
    assert AppLogEvent.query.filter_by(signature='x-new-test').count() == 1
    assert SystemSample.query.filter_by(metric='x_old_metric').count() == 0
    assert SystemSample.query.filter_by(metric='x_new_metric').one().value == 2.0
