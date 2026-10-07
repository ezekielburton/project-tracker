"""Slowest queries over a true 24 hours: the subtraction, a reset in between,
the hourly save, and the page reading "off" while pg_stat_statements isn't loaded."""
from datetime import datetime, timedelta

from app.modules.system.collectors import snapshot as collector
from app.modules.system.lib import query_stats
from app.modules.system.models import QueryStatSample
from app.modules.system.services import slow_queries

NOW = datetime(2031, 3, 4, 10, 0, 0)


def test_the_window_subtracts_the_baseline():
    ran = query_stats.window([(1, 110, 5500.0), (2, 40, 400.0), (3, 7, 70.0)],
                             {1: (100, 5000.0), 2: (40, 400.0)})
    assert ran == {1: (10, 500.0), 3: (7, 70.0)}  # 2 never ran in the window


def test_a_reset_in_between_counts_from_zero():
    assert query_stats.window([(1, 5, 900.0)], {1: (100, 5000.0)}) == {1: (5, 900.0)}


def test_query_text_is_one_short_line():
    assert query_stats.short_text('SELECT  a\n  FROM b') == 'SELECT a FROM b'
    long = query_stats.short_text('x' * 500)
    assert len(long) == query_stats.TEXT_LENGTH and long.endswith('…')
    assert query_stats.short_text(None) == ''


def test_without_the_extension_nothing_is_saved_and_the_page_reads_off(db_session):
    cur = db_session.connection().connection.cursor()
    collector.save_query_stats(cur, NOW)
    assert QueryStatSample.query.filter(QueryStatSample.ts == NOW).count() == 0
    assert slow_queries.slowest(NOW) == {'enabled': False}
    assert slow_queries.over_limit(NOW) == []


def test_the_hourly_save_keeps_27_hours(db_session, monkeypatch):
    monkeypatch.setattr(query_stats, 'read_totals', lambda cur: [(11, 5, 50.0), (12, 2, 9000.0)])
    cur = db_session.connection().connection.cursor()
    old = NOW - timedelta(hours=30)
    db_session.add(QueryStatSample(ts=old, queryid=11, calls=1, total_ms=1.0))
    db_session.flush()
    collector.save_query_stats(cur, NOW)
    assert QueryStatSample.query.filter(QueryStatSample.ts == NOW).count() == 2
    assert QueryStatSample.query.filter(QueryStatSample.ts == old).count() == 0


def _live(monkeypatch, totals, texts=None):
    monkeypatch.setattr(query_stats, 'read_totals', lambda cur: totals)
    monkeypatch.setattr(slow_queries, '_texts', lambda ids: texts or {})


def test_slowest_uses_the_sample_from_24_hours_ago(db_session, monkeypatch):
    for hours, calls, total in ((25, 10, 1000.0), (24, 20, 2000.0), (2, 90, 9000.0)):
        db_session.add(QueryStatSample(ts=NOW - timedelta(hours=hours), queryid=7, calls=calls, total_ms=total))
    db_session.flush()
    _live(monkeypatch, [(7, 26, 14000.0)], {7: 'SELECT  1'})
    found = slow_queries.slowest(NOW)
    assert found['since'] == NOW - timedelta(hours=24)
    assert found['rows'] == [{'queryid': 7, 'calls': 6, 'total_ms': 12000.0, 'mean_ms': 2000.0, 'text': 'SELECT 1'}]


def test_before_any_sample_the_totals_count_since_reset(db_session, monkeypatch):
    _live(monkeypatch, [(1, 4, 400.0), (2, 2, 3000.0)])
    found = slow_queries.slowest(NOW)
    assert found['since'] is None
    assert [row['queryid'] for row in found['rows']] == [2, 1]  # slowest on average first


def test_over_limit_needs_slow_and_repeated(db_session, monkeypatch):
    _live(monkeypatch, [(1, 3, 3600.0), (2, 1, 9000.0), (3, 50, 500.0)])
    assert [row['queryid'] for row in slow_queries.over_limit(NOW)] == [1]
