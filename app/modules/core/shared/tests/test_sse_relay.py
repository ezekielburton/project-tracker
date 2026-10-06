"""sse_relay._listen_loop: a dropped LISTEN connection is closed before the
loop reconnects. Driven with a fake psycopg2 connection; the loop is broken
out of by making the reconnect back-off sleep raise."""
import logging
import types

import pytest

from app.modules.core.shared.services import sse_relay


class _StopLoop(BaseException):
    """BaseException so _listen_loop's `except Exception` doesn't catch it."""


class _FailingCursor:
    def execute(self, sql):
        raise RuntimeError('connection dropped')


class _FakeConn:
    def __init__(self, close_raises=False):
        self.closed = False
        self.close_raises = close_raises

    def set_isolation_level(self, level):
        pass

    def cursor(self):
        return _FailingCursor()

    def close(self):
        self.closed = True
        if self.close_raises:
            raise RuntimeError('already gone')


def _fake_app():
    return types.SimpleNamespace(
        config={'SQLALCHEMY_DATABASE_URI': 'postgresql://unused'},
        logger=logging.getLogger('test_sse_relay'),
    )


def _raise_stop(seconds):
    raise _StopLoop()


@pytest.mark.parametrize('close_raises', [False, True])
def test_listen_loop_closes_the_dropped_connection(monkeypatch, close_raises):
    conn = _FakeConn(close_raises=close_raises)
    monkeypatch.setattr(sse_relay.psycopg2, 'connect', lambda uri: conn)
    monkeypatch.setattr(sse_relay.time, 'sleep', _raise_stop)

    with pytest.raises(_StopLoop):
        sse_relay._listen_loop(_fake_app())
    assert conn.closed


def test_listen_loop_survives_a_failed_connect(monkeypatch):
    def _refuse(uri):
        raise RuntimeError('database is down')

    monkeypatch.setattr(sse_relay.psycopg2, 'connect', _refuse)
    monkeypatch.setattr(sse_relay.time, 'sleep', _raise_stop)

    # Reaches the back-off sleep instead of failing on an unbound connection.
    with pytest.raises(_StopLoop):
        sse_relay._listen_loop(_fake_app())


def test_a_friction_change_rings_every_friction_subscriber():
    first = sse_relay.subscribe_friction()
    second = sse_relay.subscribe_friction()
    try:
        sse_relay._dispatch_friction_change()
        assert first.get_nowait() == 1
        assert second.get_nowait() == 1
    finally:
        sse_relay.unsubscribe_friction(first)
        sse_relay.unsubscribe_friction(second)


def test_an_unsubscribed_queue_hears_nothing():
    q = sse_relay.subscribe_friction()
    sse_relay.unsubscribe_friction(q)
    sse_relay._dispatch_friction_change()
    assert q.empty()


def test_the_friction_stream_requires_auth(client):
    assert client.get('/sse/friction').status_code in (302, 401)
