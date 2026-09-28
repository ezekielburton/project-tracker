"""Email notification prefs: saves merge into the shared blob, every toggle
account.html renders persists, the wizard's "email off" covers the same keys,
and lead-change emails follow the lead_changed toggle."""
import json
import re
from pathlib import Path

from flask import url_for

from app.modules.core.shared.models import Project, User
from app.modules.core.shared.services import notifications as svc
from app.modules.core.shared.testing import login_as

ACCOUNT_TEMPLATE = Path(__file__).resolve().parents[1] / 'templates' / 'auth' / 'account.html'


def _rendered_pref_keys():
    return set(re.findall(r"pref_row\('[^']*', '([a-z_]+)'\)", ACCOUNT_TEMPLATE.read_text()))


def _user(db_session, tag, role='designer', prefs=None):
    user = User(name=f'Prefs {tag}', email=f'prefs-{tag}@example.com', role=role,
                notification_prefs=json.dumps(prefs) if prefs is not None else None)
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()
    return user


def _prefs(user_id):
    return json.loads(User.query.get(user_id).notification_prefs or '{}')


def _save_url(app, endpoint):
    with app.test_request_context():
        return url_for(endpoint)


def test_account_save_keeps_sound_prefs_and_a_turned_off_toggle(app, client, db_session):
    user = _user(db_session, 'merge', prefs={'sound_enabled': False, 'sound_volume': 0.3, 'sound_id': None})
    login_as(client, app, user, 'password123')
    url = _save_url(app, 'auth.save_notification_prefs')

    assert client.post(url, json={'flag_reply': False, 'project_approved': True}).status_code == 200
    # A later save of a different toggle leaves the first one off.
    assert client.post(url, json={'project_approved': False}).status_code == 200

    prefs = _prefs(user.id)
    assert prefs['flag_reply'] is False
    assert prefs['project_approved'] is False
    assert prefs['sound_enabled'] is False
    assert prefs['sound_volume'] == 0.3
    assert 'sound_id' in prefs


def test_every_rendered_toggle_persists(app, client, db_session):
    user = _user(db_session, 'all', role='admin')
    login_as(client, app, user, 'password123')
    keys = _rendered_pref_keys()
    assert {'preprod_stream_approved', 'preprod_stream_uploaded', 'due_date_changed',
            'job_number_changed', 'client_spoc_changed'} <= keys

    resp = client.post(_save_url(app, 'auth.save_notification_prefs'),
                       json={k: False for k in keys} | {'not_a_pref': False})
    assert resp.status_code == 200

    prefs = _prefs(user.id)
    assert {k for k, v in prefs.items() if v is False} == keys
    for key in keys:
        assert User.query.get(user.id).wants_notification(key) is False


def test_wizard_email_off_covers_every_rendered_toggle(app, client, db_session):
    user = _user(db_session, 'wizard', prefs={'sound_id': 3})
    login_as(client, app, user, 'password123')

    resp = client.post(_save_url(app, 'wizard.complete'), json={'email_enabled': False})
    assert resp.status_code == 200

    prefs = _prefs(user.id)
    assert {k for k, v in prefs.items() if v is False} == _rendered_pref_keys()
    assert prefs['sound_id'] == 3


def test_designer_sees_the_lead_changed_toggle_only(app, client, db_session):
    user = _user(db_session, 'lead-page')
    login_as(client, app, user, 'password123')

    html = client.get(_save_url(app, 'auth.account')).get_data(as_text=True)
    assert 'data-key="lead_changed"' in html
    assert 'data-key="lead_assigned"' not in html


def test_lead_change_emails_follow_the_lead_changed_toggle(app, db_session, monkeypatch):
    cs_lead = _user(db_session, 'lead-cs', role='cs', prefs={'lead_changed': False})
    previous = _user(db_session, 'lead-prev', prefs={'lead_changed': True})
    new_lead = _user(db_session, 'lead-new')
    project = Project(name='Lead Prefs Project', cs_lead_id=cs_lead.id, created_by_id=cs_lead.id)
    db_session.add(project)
    db_session.commit()

    emailed = []
    monkeypatch.setattr(svc, '_send_notification_email',
                        lambda recipient, message, project: emailed.append(recipient.id))

    svc.notify_cs_of_lead_change(project, new_lead, '2D', triggered_by=new_lead,
                                 previous_designer=previous)

    assert emailed == [previous.id]
