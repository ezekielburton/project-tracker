"""Smoke test for the first-login account wizard (part of the profile module)."""
from flask import url_for


def test_wizard_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('wizard.complete')
    resp = client.post(url)
    assert resp.status_code in (302, 401)


def _wizard_user(db_session, email, prefs):
    import json
    from app.modules.core.shared.models import User
    u = User(name='Wiz', email=email, role='designer', notification_prefs=json.dumps(prefs))
    u.set_password('pw123456')
    db_session.add(u)
    db_session.commit()
    return u


def _complete(app, client, payload):
    with app.test_request_context():
        url = url_for('wizard.complete')
    resp = client.post(url, json=payload)
    assert resp.get_json()['success'] is True


def test_avatar_only_finish_keeps_email_opt_outs(app, client, db_session):
    # The avatar-only wizard sends no email_enabled; saved opt-outs must survive.
    import json
    from app.modules.core.shared.models import User
    from app.modules.core.shared.testing import login_as
    u = _wizard_user(db_session, 'wiz-keep@example.com', {'brief_flag': False, 'flag_reply': False})
    login_as(client, app, u, 'pw123456')
    _complete(app, client, {'sound_enabled': True, 'sound_volume': 0.5})
    prefs = json.loads(User.query.get(u.id).notification_prefs)
    assert prefs['brief_flag'] is False
    assert prefs['flag_reply'] is False
    assert prefs['sound_volume'] == 0.5


def test_email_step_still_saves_choice(app, client, db_session):
    import json
    from app.modules.core.shared.models import User
    from app.modules.core.shared.testing import login_as
    u = _wizard_user(db_session, 'wiz-email@example.com', {'brief_flag': False})
    login_as(client, app, u, 'pw123456')

    _complete(app, client, {'email_enabled': True})
    assert 'brief_flag' not in json.loads(User.query.get(u.id).notification_prefs)

    _complete(app, client, {'email_enabled': False})
    assert json.loads(User.query.get(u.id).notification_prefs)['brief_flag'] is False
