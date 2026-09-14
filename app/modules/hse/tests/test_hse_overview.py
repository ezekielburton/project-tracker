"""The front page's numbers, and the one rule they all hang off:
a metric is defined once and read, never recomputed.

Plain stubs again — lib/metrics.py and lib/overview.py read attributes and
never query, so none of this needs the app fixture.
"""
from datetime import date, timedelta

import pytest

from app.modules.hse.lib.metrics import (
    closed_on_time_rate, compliance_health, expiring_soon_count,
    expiry_registers, sla_pressure,
)
from app.modules.hse.lib.overview import (
    expiring_panel, needs_you_now, open_incident_count, tiles,
    waiting_on_others,
)
from app.modules.hse.models import HseEntry


TODAY = date(2026, 9, 14)

ENTRY_FIELDS = ('id', 'register', 'ref', 'entry_date', 'status', 'severity',
                'closed_at', 'due_at', 'waiting_on_id', 'waiting_since',
                'schedule_id', 'occurrence_date', 'asset_id')


class _Person:
    def __init__(self, name):
        self.name = name


class _Entry:
    def __init__(self, data=None, waiting_on=None, **kw):
        for name in ENTRY_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'
        self.data = data or {}
        self.waiting_on = waiting_on
        self.asset = None


def entry(**kw):
    kw.setdefault('id', 1)
    kw.setdefault('ref', 'INC-0001')
    kw.setdefault('register', 'incidents')
    kw.setdefault('entry_date', date(2026, 9, 1))
    return _Entry(**kw)


def cert(days_left, **kw):
    """A compliance item expiring in `days_left` days — negative for gone."""
    kw.setdefault('id', 100 + days_left)
    kw.setdefault('ref', f'COM-{abs(days_left):04d}')
    return _Entry(register='compliance_renewal',
                  entry_date=date(2026, 1, 1),
                  due_at=TODAY + timedelta(days=days_left),
                  data={'item': kw.pop('item', f'Item {days_left}')}, **kw)


def test_the_stub_only_uses_real_columns():
    columns = {c.key for c in HseEntry.__table__.columns}
    missing = [n for n in ENTRY_FIELDS if n not in columns]
    assert not missing, ', '.join(missing)


# --- compliance health ----------------------------------------------------

def test_health_is_items_valid_today_over_items_tracked():
    """The definition agreed for the performance page, used by the tile."""
    health = compliance_health([cert(100), cert(10), cert(-5)], TODAY)
    assert health['total'] == 3
    assert health['valid'] == 2
    assert health['percent'] == 67


def test_health_names_what_lapsed_rather_than_hiding_it():
    """A page that only flatters is worth nothing in the room."""
    health = compliance_health([cert(100), cert(-5, item='Fire certificate')], TODAY)
    assert [e.data['item'] for e in health['lapsed']] == ['Fire certificate']


def test_lapsed_items_come_back_oldest_first():
    health = compliance_health([cert(-2), cert(-40), cert(-9)], TODAY)
    assert [e.due_at for e in health['lapsed']] == sorted(e.due_at for e in health['lapsed'])


def test_nothing_tracked_reads_as_unknown_not_as_zero():
    health = compliance_health([], TODAY)
    assert health['percent'] is None
    assert health['total'] == 0


def test_health_only_counts_registers_whose_status_is_an_expiry():
    """An incident has no expiry date and must not drag the percentage."""
    assert 'incidents' not in expiry_registers()
    health = compliance_health([entry(status='Open'), cert(30)], TODAY)
    assert health['total'] == 1


def test_expiring_soon_uses_the_workbooks_own_window():
    assert expiring_soon_count([cert(29), cert(31), cert(-1)], TODAY) == 1


# --- the SLA clock --------------------------------------------------------

def test_sla_pressure_excludes_time_parked_with_someone_else():
    """Twelve days open on a seven-day SLA. Six of them were spent waiting
    on the production manager, so only six are his — he has a day left,
    where the raw age would have said he was five days over."""
    e = entry(entry_date=date(2026, 9, 2), severity='High', status='Open',
              waiting_since=date(2026, 9, 8))
    assert sla_pressure(e, TODAY) == -1


def test_the_same_entry_is_over_its_sla_without_the_waiting():
    """The pair matters: the only difference is who was holding it."""
    e = entry(entry_date=date(2026, 9, 2), severity='High', status='Open')
    assert sla_pressure(e, TODAY) == 5


def test_sla_pressure_is_unknown_without_a_severity():
    assert sla_pressure(entry(status='Open'), TODAY) is None


def test_a_closed_entry_is_under_no_pressure():
    e = entry(severity='High', status='Closed', closed_at=date(2026, 9, 3))
    assert sla_pressure(e, TODAY) is None


def test_the_on_time_rate_is_unknown_when_nothing_closed():
    """A quiet month has no rate, and 0% would read as failure."""
    rate = closed_on_time_rate([], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert rate['percent'] is None


# --- needs you now --------------------------------------------------------

def test_needs_you_now_puts_the_furthest_past_its_sla_first():
    late = entry(id=1, ref='INC-0001', entry_date=date(2026, 8, 1),
                 severity='High', status='Open')
    fresh = entry(id=2, ref='INC-0002', entry_date=date(2026, 9, 13),
                  severity='High', status='Open')
    rows = needs_you_now([fresh, late], TODAY)['rows']
    assert [r['ref'] for r in rows] == ['INC-0001', 'INC-0002']
    assert rows[0]['over_sla'] > 0
    assert rows[1]['over_sla'] == 0


def test_work_parked_with_someone_else_is_not_on_his_list():
    """He has already chased it. Crowding it in beside work he can do makes
    the list useless."""
    parked = entry(id=3, ref='INC-0003', severity='High', status='Open',
                   waiting_on_id=7, waiting_since=date(2026, 9, 2),
                   waiting_on=_Person('A. Rahman'))
    assert needs_you_now([parked], TODAY)['total'] == 0
    waiting = waiting_on_others([parked], TODAY)
    assert waiting['total'] == 1
    assert waiting['rows'][0]['person'] == 'A. Rahman'
    assert waiting['rows'][0]['days'] == 12


def test_closed_and_logged_work_is_not_outstanding():
    closed = entry(id=4, status='Closed', closed_at=date(2026, 9, 5))
    log = _Entry(id=5, register='toolbox_talk', ref='TBT-0001',
                 entry_date=date(2026, 9, 9))
    assert needs_you_now([closed, log], TODAY)['total'] == 0


def test_the_panel_caps_its_rows_and_says_how_many_more():
    """The Overview is a place to start work, not a second register."""
    many = [entry(id=i, ref=f'INC-{i:04d}', severity='High', status='Open',
                  entry_date=date(2026, 8, 1)) for i in range(1, 11)]
    panel = needs_you_now(many, TODAY)
    assert panel['total'] == 10
    assert len(panel['rows']) == 6
    assert panel['more'] == 4


def test_open_incidents_counts_the_whole_group_not_one_register():
    rows = [entry(id=1, status='Open'),
            _Entry(id=2, register='first_aid', ref='FA-0001',
                   entry_date=date(2026, 9, 2), status='Open'),
            _Entry(id=3, register='general_inspection', ref='INS-0001',
                   entry_date=date(2026, 9, 2), status='Open')]
    assert open_incident_count(rows) == 2


# --- the expiring panel ---------------------------------------------------

def test_the_expiring_panel_puts_what_lapsed_above_what_is_about_to():
    health = compliance_health([cert(10, item='Soon'), cert(-3, item='Gone')], TODAY)
    rows = expiring_panel(health, TODAY)['rows']
    assert [r['title'] for r in rows] == ['Gone', 'Soon']
    assert rows[0]['lapsed'] is True
    assert rows[1]['lapsed'] is False


# --- the tiles ------------------------------------------------------------

def test_the_tiles_read_the_shared_definitions_rather_than_their_own():
    """Compliance health on the tile must equal compliance health anywhere
    else — that equality is the whole reason the definition is shared."""
    entries = [cert(100), cert(-5), entry(status='Open', severity='High')]
    counts, health = tiles([], entries, date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert counts['health_percent'] == health['percent']
    assert counts['health_valid'] == health['valid']
    assert health == compliance_health(entries, TODAY)


def test_coverage_on_the_tile_is_the_calendars_coverage():
    counts, _ = tiles([], [], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert counts['done'] == 0
    assert counts['due'] == 0
