"""
The Daily log register over HTTP: new entries start Open, resolving stamps
the resolved date, only open logs count as open work, and files attach.
"""
from datetime import date
from io import BytesIO

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib.overview import needs_you_now
from app.modules.hse.lib.query import dashboard_entries, open_counts_by_register
from app.modules.hse.models import HseEntry, HsePerson, HseReference
from app.modules.hse.routes import attachments


def _url(app, endpoint, **kw):
    with app.test_request_context():
        return url_for(endpoint, **kw)


def _setup(app, client, db_session):
    user = User(name='Daily Log Officer', email='hse-daily-log@example.com', role='hse')
    user.set_password('password123')
    place = HseReference(kind='location', label='Daily Log Yard')
    person = HsePerson(name='Daily Log Walker')
    db_session.add_all([user, place, person])
    db_session.flush()
    login_as(client, app, user, 'password123')
    return {'entry_date': date.today().isoformat(), 'location': str(place.id),
            'description': 'Blocked fire exit by bay 3', 'severity': 'High',
            'reported_by': str(person.id), 'status': 'Open'}


def test_the_new_entry_form_starts_open(app, client, db_session):
    _setup(app, client, db_session)
    html = client.get(_url(app, 'hse.new_entry_form', register_key='daily_log')).get_data(as_text=True)
    assert '<option value="Open" selected>Open</option>' in html
    assert 'data-closed-status="Resolved" data-closed-field="closed_at"' in html


def test_a_log_is_open_until_resolved(app, client, db_session):
    payload = _setup(app, client, db_session)
    res = client.post(_url(app, 'hse.create_entry', register_key='daily_log'), json=payload)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['ref'] == 'DL-0001'
    entry = db_session.get(HseEntry, res.get_json()['id'])
    assert entry.status == 'Open' and entry.closed_at is None

    assert open_counts_by_register().get('daily_log') == 1
    assert entry.id in [r['entry'].id for r in needs_you_now(dashboard_entries())['rows']]

    # Resolved with no date: the server stamps today.
    res = client.patch(_url(app, 'hse.update_entry', entry_id=entry.id),
                       json=dict(payload, status='Resolved', closed_at=''))
    assert res.status_code == 200, res.get_json()
    db_session.refresh(entry)
    assert entry.closed_at == date.today()

    assert 'daily_log' not in open_counts_by_register()
    assert entry.id not in [r['entry'].id for r in needs_you_now(dashboard_entries())['rows']]


def test_reopening_a_resolved_log_clears_its_date_and_counts_it_open(app, client, db_session):
    payload = _setup(app, client, db_session)
    entry_id = client.post(_url(app, 'hse.create_entry', register_key='daily_log'),
                           json=dict(payload, status='Resolved', closed_at='2026-09-03')
                           ).get_json()['id']
    assert 'daily_log' not in open_counts_by_register()

    # The form still carries the old date; the server drops it.
    res = client.patch(_url(app, 'hse.update_entry', entry_id=entry_id),
                       json=dict(payload, status='Open', closed_at='2026-09-03'))
    assert res.status_code == 200, res.get_json()
    entry = db_session.get(HseEntry, entry_id)
    db_session.refresh(entry)
    assert entry.closed_at is None
    assert open_counts_by_register().get('daily_log') == 1


def test_a_resolved_date_the_user_sends_is_kept(app, client, db_session):
    payload = _setup(app, client, db_session)
    res = client.post(_url(app, 'hse.create_entry', register_key='daily_log'),
                      json=dict(payload, entry_date='2026-09-01', status='Resolved',
                                closed_at='2026-09-03'))
    assert res.status_code == 201, res.get_json()
    entry = db_session.get(HseEntry, res.get_json()['id'])
    assert entry.closed_at == date(2026, 9, 3)


def test_the_register_page_and_group_url_load(app, client, db_session):
    _setup(app, client, db_session)
    assert client.get(_url(app, 'hse.group_page', group_key='daily_log')).status_code == 302
    html = client.get(_url(app, 'hse.register_page', group_key='daily_log',
                           register_key='daily_log')).get_data(as_text=True)
    assert '<h1 class="hse-title">Daily log</h1>' in html
    assert 'module-rail-item--active' in html.split('>Daily log')[0].rsplit('<a ', 1)[-1]


def test_a_log_takes_attachments_under_its_own_folder(app, client, db_session, monkeypatch):
    stored = []
    monkeypatch.setattr(attachments, 'upload_app_file',
                        lambda data, folder, name: stored.append(f'{folder}/{name}'))
    payload = _setup(app, client, db_session)
    entry_id = client.post(_url(app, 'hse.create_entry', register_key='daily_log'),
                           json=payload).get_json()['id']

    res = client.post(_url(app, 'hse.upload_attachment', entry_id=entry_id),
                      data={'file': (BytesIO(b'img'), 'exit.jpg')},
                      content_type='multipart/form-data')
    assert res.status_code == 201, res.get_json()
    assert stored == ['/HSE/Daily log/DL-0001/exit.jpg']
