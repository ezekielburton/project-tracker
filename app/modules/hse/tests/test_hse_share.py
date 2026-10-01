"""
Sharing (lib/share.py): the My performance CSV, and emailing a report's
headline figures with a link. No attachment; mail goes through the app's
Flask-Mail setup and is refused while MAIL_ENABLED is off.
"""
import csv
import io

import pytest
from flask import url_for

from app.modules.core.shared.extensions import mail
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib import share


def _user(db_session, name, role, email=None, active=True):
    user = User(name=name, email=email or f'{name.lower().replace(" ", ".")}@share.example.com',
                role=role, is_active=active)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def people(db_session):
    return {
        'officer': _user(db_session, 'Share Officer', 'hse'),
        'manager': _user(db_session, 'Share Manager', 'management'),
        'designer': _user(db_session, 'Share Designer', 'designer'),
        'gone': _user(db_session, 'Share Gone', 'management', active=False),
    }


@pytest.fixture
def outbox(app, monkeypatch):
    """Mail switched on, sends captured instead of delivered."""
    sent = []
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', 'true')
    monkeypatch.setattr(mail, 'send', lambda message: sent.append(message))
    return sent


# --- recipients and the email -----------------------------------------------

def test_only_active_people_who_can_open_hse_are_offered(app, people):
    offered = {u.id for u in share.recipients(people['officer'])}
    assert people['manager'].id in offered
    assert people['designer'].id not in offered, 'no view_hse'
    assert people['gone'].id not in offered, 'inactive'
    assert people['officer'].id not in offered, 'the sender is copied, not listed'


def test_figures_read_as_value_and_comparison():
    rows = share.figures([
        {'label': 'Closed on time', 'value': 80, 'unit': '%', 'delta': {'from': 70}, 'delta_unit': '%'},
        {'label': 'Days lost', 'value': 3, 'unit': 'days', 'delta': {'from': 5}},
        {'label': 'Since the last LTI', 'value': None, 'unit': 'days', 'delta': None},
    ])
    assert rows == [('Closed on time', '80%', 'from 70%'), ('Days lost', '3 days', 'from 5 days'),
                    ('Since the last LTI', '—', '')]


def test_send_mails_the_chosen_people_and_copies_the_sender(app, people, outbox):
    chosen = share.send(people['officer'], [people['manager'].id, people['designer'].id, 'x'],
                        '<b>see this</b>', 'HSE performance', 'September 2026',
                        [('Incidents', '2', 'from 1')], 'https://example.com/r')
    assert chosen == [people['manager']], 'anyone not on the list is dropped'
    message = outbox[0]
    assert message.recipients == [people['manager'].email]
    assert message.cc == [people['officer'].email]
    assert 'September 2026' in message.subject
    assert '&lt;b&gt;see this&lt;/b&gt;' in message.html, 'the note is escaped'
    assert 'https://example.com/r' in message.html and 'https://example.com/r' in message.body


def test_send_refuses_when_mail_is_off_or_nobody_is_picked(app, people, monkeypatch):
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', 'false')
    with pytest.raises(share.ShareError) as off:
        share.send(people['officer'], [people['manager'].id], '', 't', 'p', [], 'l')
    assert off.value.status == 503
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', 'true')
    with pytest.raises(share.ShareError) as nobody:
        share.send(people['officer'], [people['designer'].id], '', 't', 'p', [], 'l')
    assert nobody.value.status == 400
    with pytest.raises(share.ShareError):
        share.send(people['officer'], [people['manager'].id], 'x' * 1001, 't', 'p', [], 'l')


def test_a_failed_send_is_reported_not_raised(app, people, monkeypatch):
    monkeypatch.setitem(app.config, 'MAIL_ENABLED', 'true')

    def boom(message):
        raise OSError('smtp down')
    monkeypatch.setattr(mail, 'send', boom)
    with pytest.raises(share.ShareError) as err:
        share.send(people['officer'], [people['manager'].id], '', 't', 'p', [], 'l')
    assert err.value.status == 502


# --- the routes -------------------------------------------------------------

def _urls(app):
    with app.test_request_context():
        return {
            'csv': url_for('hse.performance_csv', view='month', month='2026-09'),
            'page': url_for('hse.performance', view='month', month='2026-09'),
            'share': url_for('hse.performance_share', view='month', month='2026-09'),
            'report_share': url_for('hse.statistics_report_share', kind='week', at='2026-09-14'),
            'bad_share': url_for('hse.statistics_report_share', kind='year'),
        }


def test_the_csv_downloads_the_period_shown(app, client, people):
    login_as(client, app, people['officer'], 'password123')
    res = client.get(_urls(app)['csv'])
    assert res.status_code == 200 and res.mimetype == 'text/csv'
    assert 'hse-performance-month-2026-09.csv' in res.headers['Content-Disposition']
    rows = list(csv.reader(io.StringIO(res.get_data(as_text=True))))
    assert rows[0] == ['HSE My performance', 'September 2026']
    assert ['Measure', 'This period', 'Previous period', 'Unit'] in rows
    assert rows[-1][0] == 'Sep 2026'


def test_the_page_offers_csv_and_email(app, client, people):
    login_as(client, app, people['officer'], 'password123')
    html = client.get(_urls(app)['page']).get_data(as_text=True)
    assert 'data-share-open' in html and 'hse-share-person' in html and '>CSV<' in html


def test_emailing_my_performance(app, client, people, outbox):
    login_as(client, app, people['officer'], 'password123')
    res = client.post(_urls(app)['share'], json={'to': [people['manager'].id], 'note': 'For Monday'},
                      headers={'X-Forwarded-Proto': 'https'})
    assert res.status_code == 200, res.get_json()
    assert res.get_json() == {'sent': ['Share Manager']}
    assert 'https://localhost/hse/performance/report?' in outbox[0].html, 'the proxy decides https'


def test_emailing_a_weekly_report(app, client, people, outbox):
    login_as(client, app, people['officer'], 'password123')
    urls = _urls(app)
    res = client.post(urls['report_share'], json={'to': [people['manager'].id]})
    assert res.status_code == 200, res.get_json()
    assert 'Weekly HSE report' in outbox[0].subject
    assert client.post(urls['bad_share'], json={'to': [people['manager'].id]}).status_code == 404


def test_emailing_with_nobody_picked_says_why(app, client, people, outbox):
    login_as(client, app, people['officer'], 'password123')
    res = client.post(_urls(app)['share'], json={'to': []})
    assert res.status_code == 400 and 'Pick at least one' in res.get_json()['error']
    assert outbox == []


def test_emailing_needs_view_hse(app, client, people, outbox):
    login_as(client, app, people['designer'], 'password123')
    res = client.post(_urls(app)['share'], json={'to': [people['manager'].id]})
    assert res.status_code in (302, 403)
    assert outbox == []


def test_the_page_and_csv_carry_spend(app, client, people):
    login_as(client, app, people['officer'], 'password123')
    urls = _urls(app)
    html = client.get(urls['page']).get_data(as_text=True)
    assert 'Spend — September 2026' in html and 'hse-spend-figs' in html
    rows = list(csv.reader(io.StringIO(client.get(urls['csv']).get_data(as_text=True))))
    assert any(row[:1] == ['Spend'] and row[-1] == 'AED' for row in rows)


def test_hr_can_be_sent_hse_reports(db_session):
    hr = _user(db_session, 'Share HR', 'hr', email='share-hr@example.com')
    assert hr in share.recipients()
