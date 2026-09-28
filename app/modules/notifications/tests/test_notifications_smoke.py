"""Smoke tests for the notifications module, using the shared fixtures."""
from flask import url_for


def test_poll_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('notifications.poll')
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_notifications_endpoints_registered(app):
    rules = {r.endpoint for r in app.url_map.iter_rules()}
    assert 'notifications.poll' in rules
    assert 'notifications.mark_read' in rules

def _notif_user(db_session, email, role='designer'):
    from app.modules.core.shared.models import User
    u = User(name=email.split('@')[0], email=email, role=role)
    u.set_password('pw123456')
    db_session.add(u)
    db_session.commit()
    return u


def test_mark_all_read_uses_emulated_user(app, client, db_session):
    from app.modules.core.shared.models import Notification
    from app.modules.core.shared.testing import login_as
    admin = _notif_user(db_session, 'notif-admin@example.com', role='admin')
    target = _notif_user(db_session, 'notif-target@example.com')
    for user in (admin, target):
        db_session.add(Notification(recipient_id=user.id, message='hi', notification_type='test'))
    db_session.commit()

    login_as(client, app, admin, 'pw123456')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = target.id
    with app.test_request_context():
        url = url_for('notifications.mark_all_read')
    assert client.post(url).get_json()['success'] is True

    assert Notification.query.filter_by(recipient_id=target.id, is_read=False).count() == 0
    assert Notification.query.filter_by(recipient_id=admin.id, is_read=False).count() == 1
