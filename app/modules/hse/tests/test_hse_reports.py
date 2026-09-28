"""
Weekly and monthly reports (lib/reports.py): the period, stepping between
periods, the incident log and what needs acting on. The figures themselves
are the Statistics view model, tested in test_hse_statistics.py.
"""
from datetime import date

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib import reports
from app.modules.hse.models import HseEntry


TODAY = date(2026, 9, 16)  # a Wednesday


class _Named:
    def __init__(self, label):
        self.label = label


class _Entry:
    def __init__(self, id, entry_date, register='incidents', **data):
        self.id, self.entry_date, self.register = id, entry_date, register
        self.ref = f'INC-{id:04d}'
        self.status, self.severity = 'Open', 'High'
        self.location = _Named('Yard')
        self.data = data


def test_a_week_runs_monday_to_sunday_against_the_week_before():
    w = reports.window('week', TODAY, TODAY)
    assert (w['start'], w['end']) == (date(2026, 9, 14), date(2026, 9, 20))
    assert (w['prev_start'], w['prev_end']) == (date(2026, 9, 7), date(2026, 9, 13))
    assert w['label'] == 'Week 38 · 14 Sep – 20 Sep 2026'


def test_a_month_is_the_calendar_month_against_the_month_before():
    w = reports.window('month', date(2026, 3, 9), TODAY)
    assert (w['start'], w['end']) == (date(2026, 3, 1), date(2026, 3, 31))
    assert (w['prev_start'], w['prev_end']) == (date(2026, 2, 1), date(2026, 2, 28))
    assert w['label'] == 'March 2026'


def test_a_future_date_is_pulled_back_to_today():
    assert reports.window('week', date(2027, 1, 1), TODAY)['start'] == date(2026, 9, 14)


def test_navigation_never_steps_into_the_future():
    now = reports.navigation(reports.window('week', TODAY, TODAY), TODAY)
    assert now == {'prev': '2026-09-13', 'next': None}
    back = reports.navigation(reports.window('month', date(2026, 7, 4), TODAY), TODAY)
    assert back == {'prev': '2026-06-30', 'next': '2026-08-01'}


def test_the_incident_log_is_oldest_first_and_capped():
    w = reports.window('week', TODAY, TODAY)
    entries = [_Entry(3, date(2026, 9, 16), event_class='Near miss'),
               _Entry(1, date(2026, 9, 14)),
               _Entry(2, date(2026, 9, 15), incident_type='Slip/Fall'),
               _Entry(4, date(2026, 9, 1))]
    log = reports.incident_rows(entries, w, limit=2)
    assert [r['ref'] for r in log['rows']] == ['INC-0001', 'INC-0002']
    assert (log['total'], log['more']) == (3, 1)
    assert log['rows'][0]['kind'] == 'Not marked' and log['rows'][1]['type'] == 'Slip/Fall'


def test_attention_lists_late_actions_flags_and_renewals(app, db_session):
    late = HseEntry(register='incidents', ref='ATT-1', entry_date=date(2026, 1, 1),
                    status='Open', severity='Critical', data={})
    db_session.add(late)
    db_session.flush()
    flag = {'title': 'Press', 'ref': 'PM-1', 'register_label': 'Preventive maintenance',
            'detail': '3d overdue'}
    out = reports.attention([late], [flag], TODAY)
    assert out['late']['total'] == 1 and out['late']['rows'][0]['ref'] == 'ATT-1'
    assert out['flags']['rows'][0]['detail'] == '3d overdue'
    assert out['renewals']['total'] == 0


# --- the pages --------------------------------------------------------------

def _officer(app, client, db_session):
    user = User(name='Report Officer', email='hse-report-officer@example.com', role='hse')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')


def test_both_reports_render_and_an_unknown_kind_is_404(app, client, db_session):
    _officer(app, client, db_session)
    with app.test_request_context():
        week = url_for('hse.statistics_report', kind='week')
        month = url_for('hse.statistics_report', kind='month', at='2026-03-05')
        bad_date = url_for('hse.statistics_report', kind='week', at='nonsense')
        year = url_for('hse.statistics_report', kind='year')
    html = client.get(week).get_data(as_text=True)
    assert 'Weekly HSE Report' in html and 'Page 2 of 2' in html
    html = client.get(month).get_data(as_text=True)
    assert 'Monthly HSE Report' in html and 'March 2026' in html and 'Page 3 of 3' in html
    assert client.get(bad_date).status_code == 200
    assert client.get(year).status_code == 404


def test_the_statistics_page_links_both_reports(app, client, db_session):
    _officer(app, client, db_session)
    with app.test_request_context():
        page = url_for('hse.statistics')
    html = client.get(page).get_data(as_text=True)
    assert 'Weekly report' in html and 'Monthly report' in html
