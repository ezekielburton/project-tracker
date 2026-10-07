"""Slowest queries over a true 24 hours. pg_stat_statements only keeps running
totals, so the snapshot collector saves them every hour and the Database page
subtracts the saved totals of 24 hours ago from the live ones."""
import re

ENABLED_SQL = (
    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') "
    "AND current_setting('shared_preload_libraries') LIKE '%%pg_stat_statements%%'"
)
TOTALS_SQL = (
    'SELECT queryid, sum(calls), sum(total_exec_time) FROM pg_stat_statements '
    'WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) '
    'AND queryid IS NOT NULL GROUP BY queryid'
)
TEXTS_SQL = (
    'SELECT queryid, min(query) FROM pg_stat_statements '
    'WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) '
    'AND queryid = ANY(%s) GROUP BY queryid'
)
_INSERT = 'INSERT INTO query_stat_samples (ts, queryid, calls, total_ms) VALUES %s'
TEXT_LENGTH = 140


def read_totals(cur):
    """[(queryid, calls, total_ms)] for this database, or None when
    pg_stat_statements isn't loaded."""
    cur.execute(ENABLED_SQL)
    if not cur.fetchone()[0]:
        return None
    cur.execute(TOTALS_SQL)
    return [(queryid, int(calls), float(total)) for queryid, calls, total in cur.fetchall()]


def save(cur, now, keep):
    """Save this hour's totals and drop samples past `keep`; returns the row
    count, or None when pg_stat_statements isn't loaded. The caller commits."""
    from psycopg2.extras import execute_values
    totals = read_totals(cur)
    if totals is None:
        return None
    if totals:
        execute_values(cur, _INSERT, [(now, queryid, calls, total) for queryid, calls, total in totals])
    cur.execute('DELETE FROM query_stat_samples WHERE ts < %s', (now - keep,))
    return len(totals)


def window(current, baseline):
    """{queryid: (calls, total_ms)} run between the baseline and now. A query
    whose calls went down was reset in between, so its totals count from zero."""
    ran = {}
    for queryid, calls, total in current:
        before_calls, before_total = baseline.get(queryid, (0, 0.0))
        if calls < before_calls:
            before_calls, before_total = 0, 0.0
        if calls > before_calls:
            ran[queryid] = (calls - before_calls, max(total - before_total, 0.0))
    return ran


def short_text(query):
    """One line, whitespace collapsed, cut to TEXT_LENGTH."""
    line = re.sub(r'\s+', ' ', query or '').strip()
    return line if len(line) <= TEXT_LENGTH else line[:TEXT_LENGTH - 1] + '…'
