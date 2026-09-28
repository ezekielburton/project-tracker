"""
Statistics (lib/statistics.py): the period and its comparison, the tiles,
the incident chart and breakdown, and the five area cards. Everything is
worked out from the registers when shown.
"""
from datetime import date

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib import statistics as stats


TODAY = date(2026, 9, 14)


class _Named:
    def __init__(self, label):
        self.label = label


class _Entry:
    """Stands in for an HseEntry; lib code reads attributes only."""
    _next = 0

    def __init__(self, register, entry_date, status=None, closed_at=None,
                 location=None, asset=None, asset_id=None, severity=None, **data):
        _Entry._next += 1
        self.id = _Entry._next
        self.ref = f'X-{self.id}'
        self.register, self.entry_date, self.status = register, entry_date, status
        self.closed_at, self.severity = closed_at, severity
        self.location = _Named(location) if location else None
        self.asset = _Named(asset) if asset else None
        self.asset_id = asset_id
        self.data = data


def _window(view='month', year=None):
    return stats.period(view, year, TODAY)


# --- the period -------------------------------------------------------------

def test_this_month_runs_to_today_against_the_same_days_last_month():
    w = _window('month')
    assert (w['start'], w['end']) == (date(2026, 9, 1), TODAY)
    assert (w['prev_start'], w['prev_end']) == (date(2026, 8, 1), date(2026, 8, 14))


def test_last_three_months_starts_two_months_back():
    w = _window('quarter')
    assert (w['start'], w['end']) == (date(2026, 7, 1), TODAY)
    assert (w['prev_start'], w['prev_end']) == (date(2026, 4, 1), date(2026, 6, 14))


def test_the_current_year_is_to_date_and_a_past_year_is_whole():
    now = _window('year', 2026)
    assert (now['start'], now['end'], now['label']) == (date(2026, 1, 1), TODAY, '2026 to date')
    assert (now['prev_start'], now['prev_end']) == (date(2025, 1, 1), date(2025, 9, 14))
    past = _window('year', 2025)
    assert (past['start'], past['end'], past['label']) == (date(2025, 1, 1), date(2025, 12, 31), '2025')


def test_a_bad_period_or_future_year_falls_back():
    assert _window('bogus')['view'] == 'month'
    assert _window('year', 2031)['year'] == 2026


# --- tiles ------------------------------------------------------------------

def test_tiles_count_the_window_and_compare_with_the_one_before():
    entries = [
        _Entry('incidents', date(2026, 9, 3), event_class='Incident'),
        _Entry('incidents', date(2026, 9, 4)),  # not classified: counts as an incident
        _Entry('incidents', date(2026, 9, 5), event_class='Near miss'),
        _Entry('incidents', date(2026, 8, 2), event_class='Incident'),
        _Entry('first_aid', date(2026, 9, 6)),
        _Entry('lost_time_injury', date(2026, 9, 1), closed_at=date(2026, 9, 11)),
        _Entry('lost_time_injury', date(2026, 9, 10)),  # still off: counts to today
    ]
    tiles = {t['label']: t for t in stats.tiles(entries, _window(), TODAY)}
    assert tiles['Incidents']['value'] == 2
    assert tiles['Incidents']['delta'] == {'improved': False, 'from': 1}
    assert tiles['Incidents']['detail'] == '1 not marked incident or near miss'
    assert tiles['Near misses']['value'] == 1
    assert tiles['Near misses']['delta']['improved'] is True, 'more near misses reported is good'
    assert tiles['First aid cases']['value'] == 1
    assert tiles['Lost time injuries']['value'] == 2
    assert tiles['Days lost']['value'] == 10 + 4
    assert tiles['Since the last LTI']['value'] == 4


def test_days_since_the_last_lti_is_none_without_one():
    assert stats.days_since_last_lti([], TODAY) is None


# --- incidents --------------------------------------------------------------

def test_the_chart_covers_twelve_months_split_by_class():
    entries = [_Entry('incidents', date(2026, 9, 1), event_class='Incident'),
               _Entry('incidents', date(2026, 9, 2), event_class='Near miss'),
               _Entry('incidents', date(2025, 10, 5), event_class='Near miss')]
    series = stats.incident_series(entries, TODAY)
    assert len(series) == 12 and series[0]['label'] == 'Oct' and series[-1]['label'] == 'Sep'
    assert (series[-1]['incidents'], series[-1]['near']) == (1, 1)
    assert series[0]['near'] == 1


def test_ranked_bars_are_largest_first_with_the_tail_folded():
    rows = stats.ranked({'A': 1, 'B': 5, 'C': 3, 'D': 0}, limit=2)
    assert [(r['label'], r['value'], r['share']) for r in rows] == [('B', 5, 100), ('Other', 4, 80)]


def test_the_breakdown_names_missing_values():
    entries = [_Entry('incidents', date(2026, 9, 2), location='Yard', severity='High',
                      incident_type='Slip/Fall'),
               _Entry('incidents', date(2026, 9, 3))]
    b = stats.incident_breakdown(entries, _window())
    assert b['total'] == 2
    assert {r['label'] for r in b['by_location']} == {'Yard', 'Not recorded'}


# --- the area cards ---------------------------------------------------------

def test_inspections_count_issues_and_everything_still_open():
    entries = [
        _Entry('general_inspection', date(2026, 9, 2), 'Open', location='Yard', issue_type='Housekeeping'),
        _Entry('general_inspection', date(2026, 9, 3), 'Closed'),
        _Entry('vehicle_inspection', date(2026, 9, 4), 'Closed', issues_found='  '),
        _Entry('forklift_inspection', date(2026, 9, 5), 'Closed', issues_found='Worn fork'),
        _Entry('forklift_inspection', date(2025, 1, 5), 'In Progress'),  # old but still open
    ]
    i = stats.inspections(entries, _window())
    assert (i['done'], i['issues'], i['open']) == (4, 2, 2)
    assert i['by_area'] == [{'label': 'Yard', 'value': 1, 'share': 100}]


def test_fleet_sums_km_per_vehicle_and_completed_service_spend():
    entries = [
        _Entry('vehicle_mileage', date(2026, 9, 2), asset='Van', km=1200),
        _Entry('vehicle_mileage', date(2026, 9, 9), asset='Van', km='800'),
        _Entry('vehicle_mileage', date(2026, 9, 9), asset='Car', km=300),
        _Entry('vehicle_service', date(2026, 9, 3), 'Completed', cost='1,500'),
        _Entry('vehicle_service', date(2026, 9, 4), 'Scheduled', cost='900'),
    ]
    f = stats.fleet(entries, _window())
    assert f['km'] == '2,300' and f['services'] == 1 and f['service_spend'] == '1,500'
    assert [(r['label'], r['text']) for r in f['by_vehicle']] == [('Van', '2,000'), ('Car', '300')]


def test_pm_is_on_time_when_done_by_the_date_the_previous_job_set():
    pm = lambda day, asset_id=1: _Entry('machine_preventive', day, 'Working', asset_id=asset_id,
                                        pm_frequency='Weekly')
    entries = [pm(date(2026, 8, 25)), pm(date(2026, 9, 1)),   # due 1 Sep: on time
               pm(date(2026, 9, 10)),                         # due 8 Sep: late
               pm(date(2026, 9, 2), asset_id=2)]              # first job: not counted
    assert stats.pm_on_time(entries, date(2026, 9, 1), TODAY) == (1, 2)
    m = stats.machines(entries, _window())
    assert (m['pm_done'], m['pm_percent']) == (3, 50)


def test_stores_counts_ppe_issued_materials_issued_and_requests_by_status():
    entries = [
        _Entry('ppe_register', date(2026, 9, 2), ppe_type='Gloves', qty=3),
        _Entry('ppe_register', date(2026, 9, 3), ppe_type='Gloves'),  # no qty: one item
        _Entry('materials_in_stock', date(2025, 1, 1), item='Tape', moves=[
            {'date': '2026-09-05', 'kind': 'issued', 'qty': 4},
            {'date': '2026-09-06', 'kind': 'received', 'qty': 10},
            {'date': '2026-08-05', 'kind': 'issued', 'qty': 7}]),
        _Entry('material_request', date(2026, 9, 4), 'Issued'),
        _Entry('material_request', date(2026, 9, 5), 'Rejected'),
    ]
    s = stats.stores(entries, _window())
    assert s['ppe_total'] == 4 and s['ppe'][0]['label'] == 'Gloves'
    assert s['materials'] == [{'label': 'Tape', 'value': 4, 'share': 100}]
    by_status = {r['label']: r['value'] for r in s['by_status']}
    assert (by_status['Issued'], by_status['Rejected'], by_status['Pending']) == (1, 1, 0)


def test_training_counts_only_what_was_held():
    entries = [
        _Entry('induction_training', date(2026, 9, 2), 'Completed', attendees=5, training_type='Induction'),
        _Entry('induction_training', date(2026, 9, 3), 'Scheduled', attendees=9, training_type='Induction'),
        _Entry('toolbox_talk', date(2026, 9, 4), 'Completed', attendees=12),
        _Entry('toolbox_talk', date(2026, 9, 5), 'Cancelled', attendees=8),
    ]
    t = stats.training(entries, _window())
    assert (t['inductions'], t['talks']) == (1, 1)


# --- the page ---------------------------------------------------------------

def _officer(app, client, db_session):
    user = User(name='Stats Officer', email='hse-stats-officer@example.com', role='hse')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')


def test_the_page_renders_for_each_period(app, client, db_session):
    _officer(app, client, db_session)
    with app.test_request_context():
        urls = [url_for('hse.statistics'), url_for('hse.statistics', period='quarter'),
                url_for('hse.statistics', period='year', year=2025),
                url_for('hse.statistics', period='nonsense', year='x')]
    for url in urls:
        res = client.get(url)
        assert res.status_code == 200, url
        html = res.get_data(as_text=True)
        assert 'Incidents and near misses' in html and 'Where and what' in html


def test_the_page_needs_view_hse(app, client, db_session):
    user = User(name='Designer', email='hse-stats-designer@example.com', role='designer')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('hse.statistics')
    assert client.get(url).status_code in (302, 403)


# --- spend ------------------------------------------------------------------

def test_spend_counts_the_window_against_the_one_before():
    from app.modules.hse.lib.query import SpendRow
    rows = [SpendRow('vehicle_service', date(2026, 9, 3), {'cost': '1,500'}),
            SpendRow('machine_cost', date(2026, 9, 10), {'amount': '250.50'}),
            SpendRow('vehicle_service', date(2026, 8, 4), {'cost': '900'}),
            SpendRow('vehicle_service', date(2025, 9, 20), {'cost': '2000'})]
    s = stats.spend(rows, _window())
    assert (s['total'], s['previous']) == ('AED 1,750.50', 'AED 900')
    assert s['tile']['value'] == '1,750' and s['tile']['delta'] == {
        'improved': None, 'from': '900', 'neutral': True}, 'no better/worse for spend'
    assert [a['label'] for a in s['top']] == ['Fleet', 'Machines']
    sep = s['series'][-1]
    assert sep['label'] == 'Sep' and sep['spend'] == 1.7505 and sep['before'] == 2.0


def test_the_page_and_reports_show_spend(app, client, db_session):
    _officer(app, client, db_session)
    with app.test_request_context():
        page = url_for('hse.statistics')
        report = url_for('hse.statistics_report', kind='month')
    html = client.get(page).get_data(as_text=True)
    assert 'By month · AED thousands' in html and '>Spend<' in html
    assert 'Spend (AED)' in client.get(report).get_data(as_text=True)
