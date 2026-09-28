"""
Service-due and low-stock flags (lib/flags.py): vehicles by km, machines by
next PM date, stock at its reorder level. Shown on the Overview panel, as a
filter chip on each register, in the tables and in the rail badges.
"""
import re
from datetime import date, timedelta

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib.flags import (
    PM_SOON_DAYS, SERVICE_SOON_KM, current_services, flag_counts, flags,
    next_service_km, odometers, pm_state, rail_counts, service_state,
)
from app.modules.hse.lib.registers import VEHICLE_SERVICE
from app.modules.hse.lib.table import columns, row
from app.modules.hse.models import HseAsset, HseEntry


TODAY = date(2026, 9, 14)


class _Asset:
    def __init__(self, id, label):
        self.id, self.label = id, label


class _Entry:
    """Stands in for an HseEntry; lib code reads attributes only."""

    def __init__(self, id, register, entry_date=TODAY, asset_id=None, status=None, **data):
        self.id, self.register, self.entry_date = id, register, entry_date
        self.asset_id, self.status = asset_id, status
        self.ref = f'X-{id:04d}'
        self.data = data
        self.asset = _Asset(asset_id, f'Asset {asset_id}') if asset_id else None
        self.compliance_item = self.location = self.subject = None
        self.due_at = self.closed_at = None


def _service(id, mileage, interval, asset_id=1, status='Completed', entry_date=TODAY):
    return _Entry(id, 'vehicle_service', entry_date, asset_id, status,
                  mileage_at_service=mileage, service_interval=interval)


def _mileage(id, odometer, asset_id=1):
    return _Entry(id, 'vehicle_mileage', TODAY, asset_id, odometer=odometer)


def _pm(id, entry_date, frequency='Weekly', asset_id=7):
    return _Entry(id, 'machine_preventive', entry_date, asset_id, 'Working',
                  pm_frequency=frequency)


def _stock(id, opening, reorder, item='Gloves'):
    return _Entry(id, 'materials_in_stock', item=item, opening_stock=opening,
                  reorder_level=reorder, unit='Box')


# --- vehicles by km ---------------------------------------------------------

def test_next_service_is_the_mileage_plus_the_interval():
    assert next_service_km(_service(1, 40000, 10000)) == 50000
    assert next_service_km(_service(1, '40,000', '10000')) == 50000


def test_no_next_service_without_both_readings():
    assert next_service_km(_service(1, None, 10000)) is None
    assert next_service_km(_service(1, 40000, None)) is None
    assert next_service_km(_service(1, 40000, 0)) is None


def test_service_state_by_km_left():
    entry = _service(1, 40000, 10000)
    assert service_state(entry, 45000) == (None, 5000)
    assert service_state(entry, 50000 - SERVICE_SOON_KM) == ('soon', SERVICE_SOON_KM)
    assert service_state(entry, 50000) == ('overdue', 0)
    assert service_state(entry, 51200) == ('overdue', -1200)


def test_with_no_later_reading_the_service_mileage_stands_in():
    entry = _service(1, 40000, 800)
    assert service_state(entry, None) == ('soon', 800)
    assert service_state(entry, 30000) == ('soon', 800), 'an older reading never counts back'


def test_only_the_latest_completed_service_counts():
    done = _service(1, 40000, 10000, entry_date=TODAY - timedelta(days=30))
    booked = _service(2, 49000, 10000, status='Scheduled')
    older = _service(3, 30000, 10000, entry_date=TODAY - timedelta(days=90))
    assert current_services([done, booked, older]) == {1: done}


def test_the_highest_odometer_is_the_current_reading():
    assert odometers([_mileage(1, 41000), _mileage(2, '43,500'), _mileage(3, 42000),
                      _mileage(4, None), _mileage(5, 9000, asset_id=2)]) == {1: 43500, 2: 9000}


# --- machines by date -------------------------------------------------------

def test_pm_state_by_days_to_the_next_due():
    assert pm_state(_pm(1, TODAY - timedelta(days=8)), TODAY)[0] == 'overdue'
    assert pm_state(_pm(1, TODAY - timedelta(days=7)), TODAY)[0] == 'soon', 'due today'
    assert pm_state(_pm(1, TODAY), TODAY) == ('soon', TODAY + timedelta(days=PM_SOON_DAYS))
    assert pm_state(_pm(1, TODAY, 'Monthly'), TODAY)[0] is None
    assert pm_state(_pm(1, TODAY, 'Emergency'), TODAY) == (None, None)


# --- the combined list ------------------------------------------------------

def test_flags_lists_overdue_then_low_stock_then_due_soon():
    rows = flags([
        _service(1, 40000, 10000), _mileage(2, 49500),               # 500 km left
        _pm(3, TODAY - timedelta(days=10)),                           # 3 days overdue
        _pm(4, TODAY - timedelta(days=30), asset_id=7),               # superseded
        _stock(5, opening=3, reorder=5), _stock(6, opening=9, reorder=5, item='Tape'),
    ], TODAY)
    assert [(r['entry'].id, r['state'], r['detail']) for r in rows] == [
        (3, 'overdue', '3d overdue'),
        (5, 'low', '3 Box left'),
        (1, 'soon', '500 km left'),
    ]


def test_an_overdue_service_says_how_far_over():
    rows = flags([_service(1, 40000, 10000), _mileage(2, 51250)], TODAY)
    assert rows[0]['detail'] == '1,250 km over'


def test_flag_counts_are_per_register():
    rows = flags([_pm(1, TODAY - timedelta(days=10)), _stock(2, 1, 5), _stock(3, 0, 5, item='B')], TODAY)
    assert flag_counts(rows) == {'machine_preventive': 1, 'materials_in_stock': 2}


# --- the Vehicle service table ----------------------------------------------

def test_next_service_sits_right_after_the_mileage():
    heads = columns(VEHICLE_SERVICE)
    assert heads[heads.index('Mileage at service (km)') + 1] == 'Next service'


def _next_service_cell(entry, current, readings):
    return row(entry, VEHICLE_SERVICE, TODAY, current, readings)[
        columns(VEHICLE_SERVICE).index('Next service')]


def test_only_the_current_service_shows_the_next_one_and_it_reads_red_once_past():
    entry = _service(1, 40000, 10000)
    assert _next_service_cell(entry, set(), {})['kind'] == 'empty'
    fine = _next_service_cell(entry, {1}, {1: 41000})
    assert (fine['text'], fine['tone']) == ('50,000 km', None)
    assert _next_service_cell(entry, {1}, {1: 49500})['tone'] == 'overdue', 'due soon is bold'
    assert _next_service_cell(entry, {1}, {1: 50100})['tone'] == 'expired', 'overdue is red'


# --- pages ------------------------------------------------------------------

def _officer(app, client, db_session):
    user = User(name='Flag Officer', email='hse-flag-officer@example.com', role='hse')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')


def _seed(db_session):
    """One vehicle due soon, one fine; one machine overdue; one low line."""
    van = HseAsset(kind='vehicle', label='Flag Van')
    car = HseAsset(kind='vehicle', label='Flag Car')
    press = HseAsset(kind='machine', label='Flag Press')
    db_session.add_all([van, car, press])
    db_session.flush()
    today = date.today()
    entries = [
        HseEntry(register='vehicle_service', ref='FSRV-1', entry_date=today, asset_id=van.id,
                 status='Completed', data={'mileage_at_service': 40000, 'service_interval': 10000}),
        HseEntry(register='vehicle_mileage', ref='FMIL-1', entry_date=today, asset_id=van.id,
                 data={'km': 100, 'odometer': 49600}),
        HseEntry(register='vehicle_service', ref='FSRV-2', entry_date=today, asset_id=car.id,
                 status='Completed', data={'mileage_at_service': 10000, 'service_interval': 10000}),
        HseEntry(register='machine_preventive', ref='FPM-1', asset_id=press.id, status='Working',
                 entry_date=today - timedelta(days=20), data={'pm_frequency': 'Weekly'}),
        HseEntry(register='materials_in_stock', ref='FHSM-1', entry_date=today,
                 data={'item': 'Flag gloves', 'opening_stock': 2, 'reorder_level': 5}),
        HseEntry(register='materials_in_stock', ref='FHSM-2', entry_date=today,
                 data={'item': 'Flag tape', 'opening_stock': 20, 'reorder_level': 5}),
    ]
    db_session.add_all(entries)
    db_session.flush()


def _register_url(app, group, key, **args):
    with app.test_request_context():
        return url_for('hse.register_page', group_key=group, register_key=key, **args)


def test_the_due_chip_keeps_only_flagged_services(app, client, db_session):
    _officer(app, client, db_session)
    _seed(db_session)
    html = client.get(_register_url(app, 'fleet', 'vehicle_service', flag='due')).get_data(as_text=True)
    assert 'FSRV-1' in html and 'FSRV-2' not in html
    assert 'Next service' in html and '50,000 km' in html


def test_the_stock_register_gets_all_and_low_stock_chips(app, client, db_session):
    _officer(app, client, db_session)
    _seed(db_session)
    html = client.get(_register_url(app, 'stores', 'materials_in_stock')).get_data(as_text=True)
    assert len(re.findall(r'class="hse-chip[ "]', html)) == 2
    assert 'Low stock' in html
    low = client.get(_register_url(app, 'stores', 'materials_in_stock', flag='low')).get_data(as_text=True)
    assert 'FHSM-1' in low and 'FHSM-2' not in low


def test_an_unknown_flag_is_ignored(app, client, db_session):
    _officer(app, client, db_session)
    _seed(db_session)
    html = client.get(_register_url(app, 'stores', 'materials_in_stock', flag='due')).get_data(as_text=True)
    assert 'FHSM-1' in html and 'FHSM-2' in html


def test_rail_badges_add_flagged_items(db_session):
    _seed(db_session)
    counts = rail_counts(date.today())
    assert counts.get('vehicle_service', 0) >= 1
    assert counts.get('machine_preventive', 0) >= 1
    assert counts.get('materials_in_stock', 0) >= 1


def test_the_overview_lists_flagged_items(app, client, db_session):
    _officer(app, client, db_session)
    _seed(db_session)
    with app.test_request_context():
        url = url_for('hse.overview')
    html = client.get(url).get_data(as_text=True)
    assert 'Service &amp; stock' in html
    assert 'Flag Van' in html and 'Flag Press' in html and 'Flag gloves' in html
    assert 'Flag Car' not in html.split('Service &amp; stock')[1].split('</section>')[0]
