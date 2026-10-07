"""/healthz answers ok or down for the heartbeat, needs no login, and is never timed."""
from app.modules.system.collectors import heartbeat
from app.modules.system.lib import request_metrics
from app.modules.system.routes import health


def test_healthz_answers_ok_without_a_login(client):
    response = client.get('/healthz')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'


def test_healthz_body_is_what_the_heartbeat_expects(client):
    assert client.get('/healthz').data == heartbeat.HEALTHY_BODY


def test_healthz_is_503_when_the_database_fails(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('database gone')
    monkeypatch.setattr(health.db.session, 'execute', fail)
    response = client.get('/healthz')
    assert response.status_code == 503
    assert response.data == b'down'


def test_healthz_is_not_timed(client):
    request_metrics.drain()
    client.get('/healthz')
    assert request_metrics.drain() == []
