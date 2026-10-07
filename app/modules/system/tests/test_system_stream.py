"""The system SSE channel: the real admin only (an emulating admin keeps it),
a ping reaches every open admin page, and the collectors send it."""
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.services import sse_relay
from app.modules.core.shared.services.live_events import SYSTEM_CHANGES_CHANNEL
from app.modules.core.shared.testing import login_as
from app.modules.system.lib import notify

PASSWORD = 'password123'


def _stream_url(app):
    with app.test_request_context():
        return url_for('sse.system_stream')


def _user(db_session, tag, **fields):
    user = User(name=f'Stream {tag}', email=f'stream-{tag}@example.com', **fields)
    user.set_password(PASSWORD)
    db_session.add(user)
    db_session.flush()
    return user


def test_the_stream_refuses_a_logged_out_caller(app, client):
    assert client.get(_stream_url(app)).status_code == 403


def test_the_stream_refuses_someone_who_is_not_admin(app, client, db_session):
    login_as(client, app, _user(db_session, 'mgmt', seniority='management'), PASSWORD)
    assert client.get(_stream_url(app)).status_code == 403


def test_the_stream_opens_for_the_admin_even_while_viewing_as_someone(app, client, db_session):
    admin = _user(db_session, 'admin', is_admin=True)
    designer = _user(db_session, 'designer', department='design')
    login_as(client, app, admin, PASSWORD)
    with client.session_transaction() as session:
        session['emulating_user_id'] = designer.id
    response = client.get(_stream_url(app))
    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'
    response.close()


def test_a_system_change_rings_every_open_admin_page():
    first, second = sse_relay.subscribe_system(), sse_relay.subscribe_system()
    try:
        sse_relay._dispatch_system_change('snapshot')
        assert first.get_nowait() == 'snapshot' and second.get_nowait() == 'snapshot'
    finally:
        sse_relay.unsubscribe_system(first)
        sse_relay.unsubscribe_system(second)


def test_notify_sends_on_the_system_channel():
    class Cursor:
        def execute(self, sql, params):
            self.sent = (sql, params)
    cur = Cursor()
    notify.notify(cur, notify.HEARTBEAT)
    assert cur.sent == ('SELECT pg_notify(%s, %s)', (SYSTEM_CHANGES_CHANNEL, 'heartbeat'))
