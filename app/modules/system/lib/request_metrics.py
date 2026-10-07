"""Request timing that stays off the request path. Each request appends one
tuple to an in-memory buffer; a background loop in each worker saves the
buffer in one INSERT every FLUSH_SECONDS, on a connection outside the pool."""
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta

import psycopg2
from flask import g, request, session
from psycopg2.extras import execute_values

from app.modules.core.shared.services.sse_relay import open_streams

FLUSH_SECONDS = 10
NO_ROUTE = '(no route)'
# A worker_stats row is dropped once its worker has been silent this long.
STALE_WORKER = timedelta(hours=1)
_SKIP_BLUEPRINTS = frozenset({'sse'})
_SKIP_ENDPOINTS = frozenset({'system.healthz'})

# Bounded: during a long database outage the oldest rows go and memory stays flat.
_BUFFER = deque(maxlen=50_000)
_flusher_pid = None

_INSERT_ROWS = (
    'INSERT INTO request_metrics (ts, method, route, blueprint, status, duration_ms, '
    'queue_ms, user_id, emulating_id, page) VALUES %s'
)
_UPSERT_WORKER = (
    'INSERT INTO worker_stats (pid, sse_open, updated_at) VALUES (%s, %s, %s) '
    'ON CONFLICT (pid) DO UPDATE SET sse_open = EXCLUDED.sse_open, updated_at = EXCLUDED.updated_at'
)
_DROP_STALE_WORKERS = 'DELETE FROM worker_stats WHERE updated_at < %s'


def mark_start():
    """Note when the request arrived (before_request)."""
    g._metrics_started = time.perf_counter()
    g._metrics_arrived = time.time()


def _skipped():
    endpoint = request.endpoint or ''
    return (endpoint == 'static' or endpoint.endswith('.static')
            or endpoint in _SKIP_ENDPOINTS or request.blueprint in _SKIP_BLUEPRINTS)


def _queue_ms(arrived):
    # nginx sends X-Request-Start: t=<epoch seconds.millis> as it hands the request on.
    header = request.headers.get('X-Request-Start', '')
    if arrived is None or not header.startswith('t='):
        return None
    try:
        wait = (arrived - float(header[2:])) * 1000
    except ValueError:
        return None
    return int(wait) if 0 <= wait < 600_000 else None


def _is_page(response, rule):
    # Cards and fragments are HTML too, but they live under /api/.
    return request.method == 'GET' and response.mimetype == 'text/html' and '/api/' not in rule


def _session_user_id():
    # The login cookie holds "<id>:<fingerprint>" (User.get_id); only the id is kept.
    token = session.get('_user_id')
    if token is None:
        return None
    try:
        return int(str(token).split(':', 1)[0])
    except ValueError:
        return None


def _session_int(key):
    # Read from the login cookie, so recording never loads the user from the database.
    try:
        return int(session[key]) if key in session else None
    except (TypeError, ValueError):
        return None


def build_row(response):
    """This request's metrics row, or None when it is skipped. Reads only g,
    the request and the session cookie, so it runs no SQL."""
    started = g.pop('_metrics_started', None)
    arrived = g.pop('_metrics_arrived', None)
    if started is None or _skipped():
        return None
    user_id = _session_user_id()
    rule = request.url_rule.rule if request.url_rule is not None else NO_ROUTE
    return (
        datetime.utcnow(), request.method[:8], rule[:200], request.blueprint,
        response.status_code, int((time.perf_counter() - started) * 1000),
        _queue_ms(arrived), user_id,
        _session_int('emulating_user_id') if user_id else None,
        _is_page(response, rule),
    )


def drain():
    """Every buffered row, oldest first, leaving the buffer empty."""
    rows = []
    while True:
        try:
            rows.append(_BUFFER.popleft())
        except IndexError:
            return rows


def write(cur, rows, pid, sse_open, now):
    """Save `rows` and this worker's SSE count with one cursor; the caller commits."""
    if rows:
        execute_values(cur, _INSERT_ROWS, rows)
    cur.execute(_UPSERT_WORKER, (pid, sse_open, now))
    cur.execute(_DROP_STALE_WORKERS, (now - STALE_WORKER,))


class _Saver:
    """One connection per worker, outside the SQLAlchemy pool; reopened after a failure."""

    def __init__(self, dsn):
        self._dsn = dsn
        self._conn = None

    def save(self, rows):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._dsn)
        with self._conn, self._conn.cursor() as cur:
            write(cur, rows, os.getpid(), open_streams(), datetime.utcnow())

    def reset(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None


def flush_once(saver, logger):
    """Save everything buffered; on failure put the rows back, in order, for the next try."""
    rows = drain()
    try:
        saver.save(rows)
    except Exception as e:
        _BUFFER.extendleft(reversed(rows))
        saver.reset()
        logger.warning(f'Request metrics: save failed ({e}); {len(rows)} rows kept for the next try.')


def _flush_forever(app):
    saver = _Saver(app.config['SQLALCHEMY_DATABASE_URI'])
    while True:
        time.sleep(FLUSH_SECONDS)
        flush_once(saver, app.logger)


def _ensure_flusher(app):
    # Started by the first request in each worker, so it never runs in
    # gunicorn's master or in scripts that only build the app.
    global _flusher_pid
    if _flusher_pid == os.getpid():
        return
    _flusher_pid = os.getpid()
    threading.Thread(target=_flush_forever, args=(app,), name='request-metrics', daemon=True).start()


def init_request_metrics(app):
    """Register the timing hooks. Under gevent the loop's thread is a greenlet;
    under tests the loop never starts and tests drain the buffer themselves."""
    autosave = not app.config.get('TESTING')

    @app.before_request
    def _metrics_start():
        mark_start()

    @app.after_request
    def _metrics_finish(response):
        try:
            row = build_row(response)
            if row is not None:
                _BUFFER.append(row)
                if autosave:
                    _ensure_flusher(app)
        except Exception:
            pass  # timing must never turn a good response into an error
        return response
