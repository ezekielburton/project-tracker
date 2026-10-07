"""The Reports pages and actions: admin only on the real user, and each
action does what it says."""
import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.reports.lib import send, settings
from app.modules.reports.models import ReportRecipient

PAGES = ['reports.generate_page', 'reports.history_page', 'reports.recipients_page']
APIS = ['reports.api_generate', 'reports.api_recipients', 'reports.api_auto_send']


def _user(db_session, tag, role):
    u = User(name=f'Reports {tag}', email=f'reports-routes-{tag}@example.com', role=role)
    u.set_password('password123')
    db_session.add(u)
    db_session.flush()
    return u


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


@pytest.mark.parametrize('endpoint', PAGES)
def test_logged_out_cannot_open_pages(app, client, endpoint):
    assert client.get(_url(app, endpoint)).status_code in (302, 401)


@pytest.mark.parametrize('role', ['management', 'cs', 'designer'])
@pytest.mark.parametrize('endpoint', PAGES)
def test_pages_refuse_non_admins(app, client, db_session, role, endpoint):
    login_as(client, app, _user(db_session, f'{role}-{endpoint[-6:]}', role), 'password123')
    assert client.get(_url(app, endpoint)).status_code == 403


@pytest.mark.parametrize('endpoint', APIS)
def test_apis_refuse_non_admins(app, client, db_session, endpoint):
    login_as(client, app, _user(db_session, f'api-{endpoint[-6:]}', 'management'), 'password123')
    assert client.post(_url(app, endpoint), json={}).status_code == 403


@pytest.mark.parametrize('endpoint', PAGES)
def test_pages_open_for_an_admin(app, client, db_session, endpoint):
    login_as(client, app, _user(db_session, f'admin-{endpoint[-6:]}', 'admin'), 'password123')
    assert client.get(_url(app, endpoint)).status_code == 200


def test_an_emulating_admin_keeps_the_pages(app, client, db_session):
    admin = _user(db_session, 'emu-admin', 'admin')
    designer = _user(db_session, 'emu-designer', 'designer')
    login_as(client, app, admin, 'password123')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id
    assert client.get(_url(app, 'reports.generate_page')).status_code == 200


def test_generate_needs_a_period_and_a_report(app, client, db_session):
    login_as(client, app, _user(db_session, 'gen-bad', 'admin'), 'password123')
    r = client.post(_url(app, 'reports.api_generate'), json={'kind': 'weekly', 'start': '2026-09-28', 'reports': []})
    assert r.status_code == 400


def test_generate_and_send_pass_through(app, client, db_session, monkeypatch):
    admin = _user(db_session, 'gen-ok', 'admin')
    calls = {}
    monkeypatch.setattr(send, 'generate', lambda period, reports, made_by=None: calls.setdefault('gen', (period, reports, made_by)) and [])
    monkeypatch.setattr(send, 'deliver', lambda runs: calls.setdefault('sent', True))
    login_as(client, app, admin, 'password123')
    r = client.post(_url(app, 'reports.api_generate'),
                    json={'kind': 'weekly', 'start': '2026-10-01', 'reports': ['design', 'nope'], 'send': True})
    assert r.status_code == 200
    period, reports, made_by = calls['gen']
    assert (period.start.isoformat(), reports, made_by.id) == ('2026-09-28', ['design'], admin.id)
    assert calls.get('sent')


def test_recipients_add_and_remove(app, client, db_session):
    admin = _user(db_session, 'rec-admin', 'admin')
    head = _user(db_session, 'rec-head', 'cs')
    login_as(client, app, admin, 'password123')
    url = _url(app, 'reports.api_recipients')

    assert client.post(url, json={'report': 'client_servicing', 'user_id': head.id, 'add': True}).status_code == 200
    assert ReportRecipient.query.filter_by(report='client_servicing', user_id=head.id).count() == 1
    assert client.post(url, json={'report': 'client_servicing', 'user_id': head.id, 'add': False}).status_code == 200
    assert ReportRecipient.query.filter_by(report='client_servicing', user_id=head.id).count() == 0


def test_auto_send_switch(app, client, db_session):
    login_as(client, app, _user(db_session, 'auto-admin', 'admin'), 'password123')
    url = _url(app, 'reports.api_auto_send')
    assert client.post(url, json={'report': 'design', 'kind': 'monthly', 'enabled': False}).status_code == 200
    assert not settings.switch_state('design', 'monthly')
    assert client.post(url, json={'report': 'nope', 'kind': 'monthly', 'enabled': False}).status_code == 400


def test_download_of_a_missing_run_is_404(app, client, db_session):
    login_as(client, app, _user(db_session, 'dl-admin', 'admin'), 'password123')
    assert client.get(_url(app, 'reports.download', run_id=999999)).status_code == 404
