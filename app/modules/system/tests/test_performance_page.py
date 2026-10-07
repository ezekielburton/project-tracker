"""What the Performance page reads from request metrics: response times and
the error rate, hourly points, page load by module (whole pages only), the
slowest routes, and the workers card."""
from datetime import datetime, timedelta

from app.modules.system.models import RequestMetric
from app.modules.system.services import performance

NOW = datetime(2031, 3, 4, 10, 0, 0)


def _hit(db_session, ms, minutes_ago=10, status=200, route='/x-perf', blueprint='wiki', page=False,
         method='GET', queue_ms=None):
    db_session.add(RequestMetric(ts=NOW - timedelta(minutes=minutes_ago), method=method, route=route,
                                 blueprint=blueprint, status=status, duration_ms=ms, page=page,
                                 queue_ms=queue_ms))


def test_summary_reads_average_p95_and_errors(db_session):
    for ms in range(10, 1010, 10):  # 100 requests, 10..1000 ms
        _hit(db_session, ms)
    _hit(db_session, 50, status=500)
    _hit(db_session, 99_999, minutes_ago=60 * 25)  # outside the window
    db_session.flush()
    found = performance.summary({'workers': {'alive': 4, 'total': 4}}, NOW)
    assert found['requests'] == 101
    assert 490 <= found['avg_ms'] <= 510
    assert 940 <= found['p95_ms'] <= 960 and found['p95_state'] == 'amber' and found['p95_pct'] == 100
    assert found['errors'] == 1 and found['error_pct'] == 1.0 and found['error_state'] == 'amber'
    assert found['workers'] == 4


def test_summary_with_no_requests(db_session):
    found = performance.summary({}, NOW)
    assert found['requests'] == 0 and found['avg_ms'] is None and found['p95_state'] == 'grey'
    assert found['error_pct'] is None and found['error_state'] == 'grey'


def test_response_series_has_a_point_per_hour(db_session):
    _hit(db_session, 100, minutes_ago=10)
    _hit(db_session, 300, minutes_ago=15)
    _hit(db_session, 50, minutes_ago=200)
    db_session.flush()
    series = performance.response_series(NOW)
    assert [value for _, value in series['avg']] == [50.0, 200.0]
    assert len(series['p95']) == 2


def test_page_load_counts_whole_pages_by_module(db_session):
    for ms in (100, 200, 900):
        _hit(db_session, ms, page=True, blueprint='wiki', minutes_ago=60 * 24 * 3)
    _hit(db_session, 5000, page=False, blueprint='wiki')                # a card or data call
    _hit(db_session, 700, page=True, blueprint='projects')             # the dashboard's blueprint
    _hit(db_session, 9000, page=True, blueprint='wiki', minutes_ago=60 * 24 * 8)  # too old
    db_session.flush()
    rows = performance.page_load_by_module(NOW)
    assert rows == [{'module': 'Dashboard', 'median_ms': 700, 'loads': 1},
                    {'module': 'Wiki', 'median_ms': 200, 'loads': 3}]


def test_slowest_routes_need_three_calls(db_session):
    for ms in (900, 1000, 1100):
        _hit(db_session, ms, route='/x-slow')
    for ms in (10, 20, 30):
        _hit(db_session, ms, route='/x-fast')
    _hit(db_session, 50_000, route='/x-once')
    db_session.flush()
    rows = performance.slowest_routes(NOW)
    assert [row['route'] for row in rows] == ['/x-slow', '/x-fast']
    assert rows[0]['avg_ms'] == 1000 and rows[0]['calls'] == 3


def test_workers_card(db_session):
    _hit(db_session, 3400, route='/dashboard', queue_ms=12)
    _hit(db_session, 20, queue_ms=4)
    db_session.flush()
    recent, old = (NOW - timedelta(hours=1)).isoformat(), (NOW - timedelta(hours=30)).isoformat()
    found = performance.workers({'workers': {'alive': 3, 'total': 4}, 'worker_starts': [recent, recent, old]}, NOW)
    assert found['state'] == 'amber' and found['restarts'] == 2
    assert found['longest'] == {'time': '3.40 s', 'route': '/dashboard'}
    assert found['queue_p95'].endswith('ms')


def test_workers_card_with_nothing_collected(db_session):
    found = performance.workers({}, NOW)
    assert found['state'] == 'grey' and found['restarts'] is None
    assert found['longest'] is None and found['queue_p95'] is None
