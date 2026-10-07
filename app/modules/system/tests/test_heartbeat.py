"""The heartbeat counts only a quick 200 'ok' as up, and saves one row per check."""
import urllib.error
from datetime import datetime

from app.modules.system.collectors import heartbeat
from app.modules.system.models import Heartbeat


class _Answer:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _answer_with(monkeypatch, outcome):
    def fake_urlopen(url, timeout):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr(heartbeat.urllib.request, 'urlopen', fake_urlopen)


def test_a_200_ok_is_up(monkeypatch):
    _answer_with(monkeypatch, _Answer(200, b'ok'))
    ok, ms = heartbeat.check()
    assert ok is True and ms >= 0


def test_any_other_body_is_down(monkeypatch):
    _answer_with(monkeypatch, _Answer(200, b'down'))
    assert heartbeat.check()[0] is False


def test_no_answer_is_down(monkeypatch):
    _answer_with(monkeypatch, urllib.error.URLError('connection refused'))
    assert heartbeat.check()[0] is False


def test_a_check_is_saved(db_session):
    cur = db_session.connection().connection.cursor()
    ts = datetime(2026, 10, 6, 12, 0)
    heartbeat.save(cur, ts, False, 5001)
    row = Heartbeat.query.filter_by(ts=ts, ms=5001).one()
    assert row.ok is False
