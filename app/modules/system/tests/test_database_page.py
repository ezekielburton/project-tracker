"""What the Database page reads: size growth and today's connection peak from
the samples, live Postgres statistics, the backup and maintenance rows, and the
slowest-queries card while pg_stat_statements is off."""
from datetime import datetime, timedelta

from app.modules.system.models import JobRun, SystemSample
from app.modules.system.services import database, slow_queries

NOW = datetime(2031, 3, 4, 10, 0, 0)  # 14:00 in Dubai
MB = 1024 ** 2


def _sample(db_session, metric, value, hours_ago):
    db_session.add(SystemSample(ts=NOW - timedelta(hours=hours_ago), metric=metric, value=value))
    db_session.flush()


def _run(db_session, job, result='ok', hours_ago=1, details=None):
    finished = NOW - timedelta(hours=hours_ago)
    db_session.add(JobRun(job=job, started_at=finished - timedelta(seconds=30), finished_at=finished,
                          result=result, details=details))
    db_session.flush()


def test_tiles_read_growth_peak_cache_and_backup(db_session):
    _sample(db_session, 'db_size', 1, hours_ago=24 * 10)
    _sample(db_session, 'db_connections', 37, hours_ago=2)      # today in Dubai
    _sample(db_session, 'db_connections', 90, hours_ago=20)     # yesterday
    _run(db_session, 'backup', hours_ago=15, details={'size': 412 * MB})
    tiles = database.tiles(NOW)
    assert tiles['growth'].startswith('+') and tiles['growth'].endswith('in 10 days')
    assert tiles['peak_today'] == 37
    assert tiles['connections'] >= 1 and tiles['max_connections'] >= tiles['connections']
    assert tiles['cache_pct'] is None or 0 <= tiles['cache_pct'] <= 100
    assert tiles['shared_buffers']
    assert tiles['backup']['size'] == '412 MB' and tiles['backup']['state'] == 'green'


def test_without_history_or_backup_those_parts_are_empty(db_session):
    tiles = database.tiles(NOW)
    assert tiles['growth'] is None and tiles['backup'] is None
    assert tiles['peak_today'] == tiles['connections']


def test_an_old_or_failed_backup_is_flagged(db_session):
    _run(db_session, 'backup', hours_ago=30)
    assert database.tiles(NOW)['backup']['state'] == 'amber'
    _run(db_session, 'backup', result='failed', hours_ago=1)
    assert database.tiles(NOW)['backup']['state'] == 'red'


def test_size_history_keeps_the_last_reading_of_each_dubai_day(db_session):
    _sample(db_session, 'db_size', 100, hours_ago=30)
    _sample(db_session, 'db_size', 120, hours_ago=26)
    _sample(db_session, 'db_size', 150, hours_ago=1)
    assert [value for _, value in database.size_history(NOW)] == [120, 150]


def test_largest_tables_lists_real_tables_biggest_first(db_session):
    tables = database.largest_tables(limit=3)
    assert len(tables) == 3
    assert tables[0]['bytes'] >= tables[1]['bytes'] >= tables[2]['bytes']
    assert all(table['size'] for table in tables)


def test_maintenance_reads_jobs_and_postgres(db_session):
    _run(db_session, 'vacuum-analyze', hours_ago=31)
    _run(db_session, 'restore-test', hours_ago=24 * 9)
    rows = database.maintenance({'db': {'pending_migrations': 0}}, NOW)
    assert rows['pending_migrations'] == 0
    assert rows['vacuum'] == {'when': 'yesterday 07:00', 'failed': False}
    assert rows['restore']['state'] == 'amber'
    assert rows['idle_in_transaction'] >= 0
    assert rows['version'][0].isdigit() and rows['max_connections'] > 0


def test_maintenance_with_nothing_run_yet(db_session):
    rows = database.maintenance({}, NOW)
    assert rows['pending_migrations'] is None and rows['vacuum'] is None and rows['restore'] is None


def test_queries_card_reads_off_without_the_extension(db_session):
    assert database.queries(NOW) == {'enabled': False}


def test_queries_card_labels_its_window(db_session, monkeypatch):
    row = {'queryid': 1, 'calls': 3, 'total_ms': 5460.0, 'mean_ms': 1820.0, 'text': 'SELECT 1'}
    monkeypatch.setattr(slow_queries, 'slowest', lambda now: {'enabled': True, 'since': since, 'rows': [row]})
    since = None
    assert database.queries(NOW)['window'] == 'since stats reset'
    since = NOW - timedelta(hours=24)
    found = database.queries(NOW)
    assert found['window'] == '24h'
    assert found['rows'] == [{'text': 'SELECT 1', 'mean': '1.82 s', 'calls': 3, 'total': '5.46 s'}]
    since = NOW - timedelta(hours=3)
    assert database.queries(NOW)['window'] == 'since 11:00'
