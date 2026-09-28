"""
Spend: the sum of every declared money field, by entry date, computed at
read time. One definition (lib/metrics.py) over one loader
(query.spend_entries), shared by the Overview panel and the register strip.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import count_queries, login_as
from app.modules.hse.lib import registers as registers_module
from app.modules.hse.lib.metrics import (
    parse_money, spend_by_area, spend_by_month, spend_of, spend_summary,
)
from app.modules.hse.lib.query import SpendRow, empty_filters, spend_entries
from app.modules.hse.lib.registers import (
    BY_KEY, HSE_REGISTERS, f, money_fields, money_registers,
)
from app.modules.hse.lib.spend import aed, spend_panel, spend_strip
from app.modules.hse.models import HseEntry


TODAY = date(2026, 9, 14)


def row(register, entry_date, **data):
    return SpendRow(register, entry_date, data)


# --- the declaration ------------------------------------------------------

def test_the_cost_registers_are_the_ones_declaring_money():
    assert [r.key for r in money_registers()] == [
        'vehicle_service', 'machine_maintenance', 'machine_preventive',
        'machine_cost', 'training_expenses']


def test_money_fields_live_in_the_json_column():
    """The loader reads money straight out of `data`."""
    promoted = [f'{r.key}.{fl.name}' for r in HSE_REGISTERS
                for fl in money_fields(r) if fl.column is not None]
    assert not promoted


# --- parsing --------------------------------------------------------------

def test_amounts_parse_from_numbers_and_text():
    assert parse_money(1200) == Decimal('1200')
    assert parse_money(12.5) == Decimal('12.5')
    assert parse_money('1,250.50') == Decimal('1250.50')
    assert parse_money('AED 300') == Decimal('300')
    assert parse_money(' 40 ') == Decimal('40')


def test_blank_negative_and_garbage_amounts_are_ignored():
    for value in (None, '', '  ', 'n/a', '-50', 'nan', 'Infinity', True, {'a': 1}, [3]):
        assert parse_money(value) is None, value


def test_an_entry_with_a_garbage_amount_spends_nothing():
    rows = [row('vehicle_service', TODAY, cost=v)
            for v in (None, '', 'n/a', '-50', '1,250.50', 300, 'AED 49.50')]
    assert sum((spend_of(r) for r in rows), Decimal(0)) == Decimal('1600')
    assert spend_of(row('vehicle_service', TODAY)) == 0
    assert spend_of(row('no_such_register', TODAY, cost=10)) == 0


def test_only_declared_money_fields_count():
    """A number that is not a money field (mileage) is not spend."""
    entry = row('vehicle_service', TODAY, cost='200', mileage_at_service='90000')
    assert spend_of(entry) == Decimal('200')


# --- periods --------------------------------------------------------------

BOUNDARY_ROWS = [
    row('training_expenses', date(2025, 12, 31), amount=5000),
    row('training_expenses', date(2026, 1, 1), amount=20000),
    row('training_expenses', date(2026, 8, 31), amount=100),
    row('training_expenses', date(2026, 9, 1), amount=10),
    row('training_expenses', date(2026, 9, 30), amount=1),
    row('training_expenses', date(2026, 10, 1), amount=1000),
]


def test_month_year_and_all_time_follow_the_entry_date():
    """Whole calendar periods: a later-dated entry this month still counts."""
    assert spend_summary(BOUNDARY_ROWS, TODAY) == {
        'month': Decimal('11'), 'year': Decimal('21111'), 'all_time': Decimal('26111')}


def test_by_month_places_each_entry_in_its_month_and_totals_the_year():
    result = spend_by_month(BOUNDARY_ROWS, 2026)
    assert result['months'][0] == 20000
    assert result['months'][7] == 100
    assert result['months'][8] == 11
    assert result['months'][9] == 1000
    assert result['total'] == Decimal('21111')
    assert spend_by_month(BOUNDARY_ROWS, 2025)['total'] == Decimal('5000')


def test_the_year_total_matches_the_summary():
    assert spend_by_month(BOUNDARY_ROWS, TODAY.year)['total'] == \
        spend_summary(BOUNDARY_ROWS, TODAY)['year']


# --- by area --------------------------------------------------------------

AREA_ROWS = [
    row('vehicle_service', date(2026, 3, 1), cost=1000),
    row('machine_maintenance', date(2026, 4, 1), cost=2000),
    row('machine_cost', date(2026, 5, 1), amount=4000),
    row('machine_cost', date(2025, 5, 1), amount=99999),   # last year
    row('training_expenses', date(2026, 6, 1), amount=3000),
]


def test_spend_by_area_splits_each_area_by_register():
    result = spend_by_area(AREA_ROWS, date(2026, 1, 1), date(2026, 12, 31))
    assert result['total'] == Decimal('10000')
    areas = {a['group']: a for a in result['areas']}
    assert list(areas) == ['fleet', 'machines', 'training']
    assert (areas['fleet']['amount'], areas['fleet']['share']) == (1000, 10)
    assert (areas['machines']['amount'], areas['machines']['share']) == (6000, 60)
    assert (areas['training']['amount'], areas['training']['share']) == (3000, 30)
    machines = {r['key']: (r['amount'], r['share']) for r in areas['machines']['registers']}
    assert machines == {'machine_maintenance': (2000, 20),
                        'machine_preventive': (0, 0),
                        'machine_cost': (4000, 40)}


def test_an_empty_year_lists_every_area_at_zero():
    result = spend_by_area([], date(2026, 1, 1), date(2026, 12, 31))
    assert result['total'] == 0
    assert [(a['group'], a['share']) for a in result['areas']] == [
        ('fleet', 0), ('machines', 0), ('training', 0)]


def test_the_panel_lists_registers_only_under_a_split_area():
    panel = spend_panel(AREA_ROWS, TODAY)
    by_label = {a['label']: a for a in panel['areas']}
    assert by_label['Machines']['amount'] == 'AED 6,000'
    assert [r['label'] for r in by_label['Machines']['registers']] == [
        'Machine maintenance', 'Preventive maintenance', 'Machine cost']
    assert by_label['Fleet']['registers'] == []
    assert [fig['value'] for fig in panel['figures']] == [
        'AED 0', 'AED 10,000', 'AED 109,999']


def test_amounts_show_fils_only_when_there_are_some():
    assert aed(Decimal('12450')) == 'AED 12,450'
    assert aed(Decimal('12450.5')) == 'AED 12,450.50'
    assert aed(Decimal('0')) == 'AED 0'
    assert aed(Decimal('1250'), unit=False) == '1,250'


def test_the_strip_blanks_months_with_no_spend():
    strip = spend_strip(BOUNDARY_ROWS, 2026, TODAY)
    assert strip['months'][0] == {'label': 'Jan', 'value': '20,000'}
    assert strip['months'][1] == {'label': 'Feb', 'value': None}
    assert strip['total'] == 'AED 21,111'


# --- the loader -----------------------------------------------------------

def _add(db_session, register, ref, entry_date, status=None, **data):
    entry = HseEntry(register=register, ref=ref, entry_date=entry_date,
                     status=status, data=data)
    db_session.add(entry)
    return entry


def test_the_loader_reads_only_cost_registers_and_their_money(db_session):
    _add(db_session, 'vehicle_service', 'SPD-1', TODAY, 'Completed',
         cost='1,200', service_type='Oil')
    _add(db_session, 'machine_cost', 'SPD-2', date(2019, 1, 5), amount=50)
    _add(db_session, 'incidents', 'SPD-3', TODAY, 'Open', cost=999)
    db_session.flush()

    rows = spend_entries()
    assert sorted((r.register, r.data) for r in rows) == [
        ('machine_cost', {'amount': '50'}),
        ('vehicle_service', {'cost': '1,200'}),
    ]
    # All time: an old entry outside the dashboard window still counts.
    assert spend_summary(rows, TODAY)['all_time'] == Decimal('1250')


def test_the_loader_is_one_query_however_many_rows(db_session):
    def queries(n):
        for i in range(n):
            _add(db_session, 'machine_cost', f'SPQ-{n}-{i}', TODAY, amount=i)
        db_session.flush()
        with count_queries() as counter:
            spend_entries()
        return counter[0]

    assert queries(2) == queries(20) == 1


def test_the_strip_follows_the_tables_status_and_search_not_its_year(db_session):
    _add(db_session, 'vehicle_service', 'SPF-1', TODAY, 'Completed', cost=100,
         service_type='Tyres')
    _add(db_session, 'vehicle_service', 'SPF-2', TODAY, 'Scheduled', cost=20)
    _add(db_session, 'vehicle_service', 'SPF-3', date(2025, 2, 1), 'Completed', cost=3)
    db_session.flush()

    def total(**changed):
        filters = dict(empty_filters(), **changed)
        rows = spend_entries(('vehicle_service',), filters)
        return spend_summary(rows, TODAY)['all_time']

    assert total() == 123
    assert total(status='Completed') == 103
    assert total(search='tyres') == 100
    assert total(year=2025) == 123, 'the year picks the months, not the rows'


def test_an_expiry_register_with_money_filters_on_its_computed_status(
        db_session, monkeypatch):
    reg = BY_KEY['vehicle_reg_insurance']
    monkeypatch.setitem(BY_KEY, reg.key, reg._replace(
        fields=reg.fields + (f('premium', 'Premium (AED)', 'money'),)))
    for ref, due, premium in (('SPX-1', TODAY + timedelta(days=200), 700),
                              ('SPX-2', TODAY - timedelta(days=5), 40)):
        row_ = _add(db_session, reg.key, ref, date(2026, 1, 1), premium=premium)
        row_.due_at = due
    db_session.flush()

    filters = dict(empty_filters(), status='Expired')
    rows = spend_entries((reg.key,), filters, TODAY)
    assert spend_summary(rows, TODAY)['all_time'] == 40


def test_a_new_money_field_is_counted_without_other_changes(db_session, monkeypatch):
    """Declaring a money field is all it takes: the loader, the metric and
    the Overview's areas pick it up."""
    mileage = BY_KEY['vehicle_mileage']
    extended = mileage._replace(fields=mileage.fields + (f('fuel', 'Fuel (AED)', 'money'),))
    monkeypatch.setitem(BY_KEY, mileage.key, extended)
    monkeypatch.setattr(registers_module, 'HSE_REGISTERS', tuple(
        extended if r.key == mileage.key else r for r in HSE_REGISTERS))

    assert 'vehicle_mileage' in [r.key for r in money_registers()]
    _add(db_session, 'vehicle_mileage', 'SPN-1', TODAY, km=40, fuel='210')
    _add(db_session, 'vehicle_service', 'SPN-2', TODAY, 'Completed', cost=90)
    db_session.flush()

    rows = spend_entries()
    fleet = next(a for a in spend_by_area(rows, date(2026, 1, 1), date(2026, 12, 31))['areas']
                 if a['group'] == 'fleet')
    assert fleet['amount'] == Decimal('300')
    assert [r['key'] for r in fleet['registers']] == ['vehicle_service', 'vehicle_mileage']


# --- the pages ------------------------------------------------------------

def _officer(app, client, db_session):
    user = User(name='HSE Spend Officer', email='hse-spend-officer@example.com', role='hse')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')


def _get(app, client, endpoint, **kw):
    with app.test_request_context():
        url = url_for(endpoint, **kw)
    res = client.get(url)
    assert res.status_code == 200
    return res.get_data(as_text=True)


def _register_page(app, client, register_key, **args):
    return _get(app, client, 'hse.register_page',
                group_key=BY_KEY[register_key].group, register_key=register_key, **args)


def _figure(html, label):
    match = re.search(
        rf'>{label}</(?:span|div)>\s*<(?:span|div) class="hse-spend-val">([^<]+)<', html)
    return match.group(1) if match else None


def _area_row(html, label):
    match = re.search(rf'<span>{label}</span>\s*<span class="hse-spend-amt">([^<]+)<', html)
    return match.group(1) if match else None


def _seed_machines(db_session):
    today = date.today()
    _add(db_session, 'machine_cost', 'SPP-1', today, amount='1,500')
    _add(db_session, 'machine_cost', 'SPP-2', date(today.year - 1, 6, 1), amount=800)
    _add(db_session, 'machine_maintenance', 'SPP-3', today, 'Completed', cost=250.5)
    db_session.flush()


def test_the_overview_shows_the_spend_panel(app, client, db_session):
    _officer(app, client, db_session)
    _seed_machines(db_session)
    html = _get(app, client, 'hse.overview')
    assert '<h2 class="hse-ov-title">Spend</h2>' in html
    assert f'By area · {date.today().year}' in html
    assert _area_row(html, 'Machines') == 'AED 1,750.50'
    assert _area_row(html, 'Machine cost') == 'AED 1,500'
    assert _figure(html, 'All time') == 'AED 2,550.50'


def test_a_cost_register_shows_its_strip_and_months(app, client, db_session):
    _officer(app, client, db_session)
    _seed_machines(db_session)
    html = _register_page(app, client, 'machine_cost')
    assert 'id="hse-spend"' in html
    assert _figure(html, 'This year') == 'AED 1,500'
    assert _figure(html, 'All time') == 'AED 2,300'
    assert f'{date.today().year} total' in html

    last_year = _register_page(app, client, 'machine_cost', year=date.today().year - 1)
    assert f'By month · {date.today().year - 1}' in last_year
    assert _figure(last_year, 'All time') == 'AED 2,300'


def test_the_strip_follows_the_status_filter(app, client, db_session):
    _officer(app, client, db_session)
    today = date.today()
    _add(db_session, 'machine_maintenance', 'SPS-1', today, 'Completed', cost=400)
    _add(db_session, 'machine_maintenance', 'SPS-2', today, 'Scheduled', cost=60)
    db_session.flush()
    assert _figure(_register_page(app, client, 'machine_maintenance'), 'This year') == 'AED 460'
    html = _register_page(app, client, 'machine_maintenance', status='Scheduled')
    assert _figure(html, 'This year') == 'AED 60'
    assert 'hse-spend-filtered' in html


def test_other_registers_show_no_strip(app, client, db_session):
    _officer(app, client, db_session)
    assert 'hse-spend' not in _register_page(app, client, 'incidents')
    assert 'hse-spend' not in _register_page(app, client, 'vehicle_mileage')


def test_the_register_pages_and_the_overview_agree(app, client, db_session):
    _officer(app, client, db_session)
    _seed_machines(db_session)
    overview = _get(app, client, 'hse.overview')
    for key in ('machine_cost', 'machine_maintenance', 'machine_preventive'):
        page = _register_page(app, client, key)
        assert _figure(page, 'This year') == _area_row(overview, BY_KEY[key].label), key

    totals = [_figure(_register_page(app, client, r.key), 'All time') for r in money_registers()]
    summed = sum(Decimal(t.replace('AED ', '').replace(',', '')) for t in totals)
    assert _figure(overview, 'All time') == aed(summed)
