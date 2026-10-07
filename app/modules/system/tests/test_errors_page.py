"""What the Errors page reads: the 24-hour tiles, groups by signature with their
latest lines, 500s by route and the raw tail."""
from datetime import datetime, timedelta

from app.modules.system.models import AppLogEvent, JobRun, RequestMetric
from app.modules.system.services import errors

NOW = datetime(2031, 3, 4, 10, 0, 0)  # 14:00 in Dubai


def _event(db_session, signature, hours_ago, level='error', message='boom', source='app', detail=None):
    db_session.add(AppLogEvent(ts=NOW - timedelta(hours=hours_ago), level=level, source=source,
                               signature=signature, message=message, detail=detail))
    db_session.flush()


def _hit(db_session, status, hours_ago=1, route='/x-errors'):
    db_session.add(RequestMetric(ts=NOW - timedelta(hours=hours_ago), method='GET', route=route,
                                 blueprint='wiki', status=status, duration_ms=10))
    db_session.flush()


def test_tiles_count_the_last_day(db_session):
    _event(db_session, 'a', 2)
    _event(db_session, 'b', 3, level='warning')
    _event(db_session, 'c', 30)  # too old
    _event(db_session, 'nas-x', 4, level='warning', source='nas_outbox')
    for status in (200, 200, 200, 500):
        _hit(db_session, status)
    db_session.add(JobRun(job='backup', started_at=NOW - timedelta(hours=5), finished_at=NOW - timedelta(hours=5),
                          result='failed'))
    db_session.flush()
    tiles = errors.tiles(NOW)
    assert (tiles['errors'], tiles['warnings']) == (1, 2)
    assert tiles['http_500'] == 1 and tiles['http_500_pct'] == 25.0
    assert tiles['failures'] == 2  # the failed backup and the NAS warning


def test_groups_count_repeats_and_keep_the_latest_lines(db_session):
    for hours in range(1, 8):
        _event(db_session, 'relay', hours, level='warning', message=f'relay {hours}', source='sse_relay', detail='trace')
    _event(db_session, 'relay', 9, level='error', message='relay down', source='sse_relay')
    _event(db_session, 'integrity', 30, message='IntegrityError on project_files')
    _event(db_session, 'ancient', 24 * 8)
    found = errors.groups(NOW)
    assert [group['signature'] for group in found] == ['relay', 'integrity']
    relay = found[0]
    assert relay['count'] == 8 and relay['error'] and relay['source'] == 'sse_relay'
    assert len(relay['lines']) == errors.LINES_SHOWN and relay['lines'][0]['message'] == 'relay 1'
    assert relay['last'] == 'today 13:00' and found[1]['first'] == 'yesterday 08:00'


def test_500s_by_route(db_session):
    _hit(db_session, 500, route='/projects/upload')
    _hit(db_session, 502, hours_ago=30, route='/projects/upload')
    _hit(db_session, 500, route='/cs/table')
    _hit(db_session, 500, hours_ago=24 * 8, route='/old')
    _hit(db_session, 404, route='/missing')
    rows = errors.routes_500(NOW)
    assert [(row['route'], row['count']) for row in rows] == [('/projects/upload', 2), ('/cs/table', 1)]


def test_tail_is_newest_first_any_level(db_session):
    _event(db_session, 'x1', 3, level='warning', message='older')
    _event(db_session, 'x2', 1, level='info', message='newest')
    tail = errors.tail(NOW)
    assert [line['message'] for line in tail[:2]] == ['newest', 'older']
