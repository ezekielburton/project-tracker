"""Request timing: what a row holds, what is skipped, that recording runs no SQL
and stays cheap, and that saved rows land in their tables."""
import logging
import time
from datetime import datetime, timedelta

import pytest
from flask import Response, session, url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.services import sse_relay
from app.modules.core.shared.testing import count_queries, login_as
from app.modules.system.lib import request_metrics as rm
from app.modules.system.models import RequestMetric, WorkerStat


@pytest.fixture(autouse=True)
def _empty_buffer():
    rm.drain()
    yield
    rm.drain()


def _row_for(app, path, status=200, headers=None, user_id=None, emulating_id=None):
    with app.test_request_context(path, headers=headers or {}):
        if user_id is not None:
            session['_user_id'] = f'{user_id}:fingerprint12'
        if emulating_id is not None:
            session['emulating_user_id'] = emulating_id
        rm.mark_start()
        return rm.build_row(Response('x', status=status))


def test_a_row_holds_the_route_rule_status_queue_wait_and_who(app):
    sent = time.time() - 0.02
    row = _row_for(app, '/dashboard/calendar', headers={'X-Request-Start': f't={sent:.3f}'},
                   user_id=5, emulating_id=9)
    _, method, route, blueprint, status, duration_ms, queue_ms, user_id, emulating_id = row
    assert (method, route, blueprint, status) == ('GET', '/dashboard/calendar', 'projects', 200)
    assert duration_ms >= 0
    assert 15 <= queue_ms < 1000
    assert (user_id, emulating_id) == (5, 9)


def test_the_user_id_is_read_from_the_real_login_token(app):
    user = User(id=4242, name='Token', email='token@example.com', password_hash='x' * 40)
    with app.test_request_context('/dashboard/calendar'):
        session['_user_id'] = user.get_id()
        rm.mark_start()
        assert rm.build_row(Response('x'))[7] == 4242


def test_without_nginx_the_queue_wait_is_empty(app):
    assert _row_for(app, '/dashboard/calendar')[6] is None


def test_emulation_is_kept_only_for_a_logged_in_user(app):
    row = _row_for(app, '/dashboard/calendar', emulating_id=9)
    assert row[7] is None and row[8] is None


def test_a_url_with_no_route_is_grouped(app):
    assert _row_for(app, '/no-such-page-xyz', status=404)[2] == rm.NO_ROUTE


@pytest.mark.parametrize('path', [
    '/static/css/main.css', '/hse/static/css/hse.css', '/sse/dashboard', '/healthz',
])
def test_static_files_streams_and_healthz_are_skipped(app, path):
    assert _row_for(app, path) is None


def test_recording_runs_no_sql(app, db_session):
    with app.test_request_context('/dashboard/calendar'):
        session['_user_id'] = '5:fingerprint12'
        rm.mark_start()
        with count_queries() as queries:
            row = rm.build_row(Response('x'))
    assert row is not None
    assert queries[0] == 0


def test_recording_a_request_costs_under_50_microseconds(app):
    runs = 10_000
    with app.test_request_context('/dashboard/calendar',
                                  headers={'X-Request-Start': f't={time.time():.3f}'}):
        session['_user_id'] = '5:fingerprint12'
        response = Response('x')
        started = time.perf_counter()
        for _ in range(runs):
            rm.mark_start()
            rm._BUFFER.append(rm.build_row(response))
        per_request_us = (time.perf_counter() - started) / runs * 1_000_000
    print(f'request metrics: {per_request_us:.1f} µs per request')
    assert per_request_us < 50


def test_a_login_is_recorded_under_the_new_user(app, client, db_session):
    user = User(name='Metrics Login', email='metrics-login@example.com')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    with app.test_request_context():
        login_rule = url_for('auth.login')

    login_as(client, app, user, 'password123')

    logins = [r for r in rm.drain() if r[1] == 'POST' and r[2] == login_rule]
    assert logins and logins[0][4] == 302 and logins[0][7] == user.id


def test_saved_rows_land_in_request_metrics_and_worker_stats(db_session):
    cur = db_session.connection().connection.cursor()
    now = datetime.utcnow()
    rm.write(cur, [(now, 'GET', '/x-metrics-test', 'projects', 200, 12, None, 5, None)], 990_001, 3, now)
    assert RequestMetric.query.filter_by(route='/x-metrics-test').count() == 1
    assert db_session.get(WorkerStat, 990_001).sse_open == 3


def test_a_silent_worker_is_dropped(db_session):
    cur = db_session.connection().connection.cursor()
    now = datetime.utcnow()
    rm.write(cur, [], 990_002, 0, now - timedelta(hours=2))
    rm.write(cur, [], 990_003, 0, now)
    assert db_session.get(WorkerStat, 990_002) is None


def test_a_failed_save_keeps_the_rows_in_order():
    class FailingSaver:
        was_reset = False

        def save(self, rows):
            raise RuntimeError('database down')

        def reset(self):
            FailingSaver.was_reset = True

    rm._BUFFER.extend(['first', 'second'])
    rm.flush_once(FailingSaver(), logging.getLogger('test_request_metrics'))
    assert rm.drain() == ['first', 'second']
    assert FailingSaver.was_reset


def test_open_streams_counts_each_subscriber():
    before = sse_relay.open_streams()
    queue = sse_relay.subscribe_dashboard()
    assert sse_relay.open_streams() == before + 1
    sse_relay.unsubscribe_dashboard(queue)
    assert sse_relay.open_streams() == before
