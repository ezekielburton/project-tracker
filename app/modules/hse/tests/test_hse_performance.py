"""My performance — the period arithmetic, the tiles, the panels and the
charts.

Plain stubs again: lib/performance.py and lib/charts.py read attributes and
never query, so none of this needs the app fixture. The stub guard below
keeps the fields honest against the real columns.
"""
from datetime import date

from app.modules.hse.lib import charts
from app.modules.hse.lib.computed import SLA_DAYS
from app.modules.hse.lib.performance import (
    age_series, closed_by_severity, compliance_panel, coverage_series,
    expiring_next, open_by_age, period, read_outs, reporting,
    schedule_coverage, sla_table, tiles, trend_months,
)
from app.modules.hse.models import HseEntry, HseSchedule


TODAY = date(2026, 9, 14)

ENTRY_FIELDS = ('id', 'register', 'ref', 'entry_date', 'status', 'severity',
                'closed_at', 'due_at', 'waiting_on_id', 'waiting_since',
                'schedule_id', 'occurrence_date', 'asset_id', 'compliance_item_id')
SCHEDULE_FIELDS = ('id', 'register', 'label', 'frequency', 'interval',
                   'weekday', 'day_of_month', 'starts_on', 'ends_on', 'active')


class _Person:
    def __init__(self, name):
        self.name = name


class _Ref:
    """A compliance certificate: a stable id, and a name that can be edited."""
    def __init__(self, id, label):
        self.id = id
        self.label = label


class _Entry:
    def __init__(self, data=None, waiting_on=None, compliance_item=None, **kw):
        for name in ENTRY_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'
        self.data = data or {}
        self.waiting_on = waiting_on
        self.compliance_item = compliance_item
        self.asset = None


class _Schedule:
    def __init__(self, assets=None, **kw):
        for name in SCHEDULE_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'
        self.assets = assets or []


def entry(**kw):
    kw.setdefault('id', 1)
    kw.setdefault('ref', 'INC-0001')
    kw.setdefault('register', 'incidents')
    return _Entry(**kw)


def sched(**kw):
    kw.setdefault('id', 5)
    kw.setdefault('register', 'general_inspection')
    kw.setdefault('label', 'Weekly walk')
    kw.setdefault('interval', 1)
    kw.setdefault('active', True)
    return _Schedule(**kw)


def test_the_stubs_only_use_real_columns():
    """A column rename must break the stubs rather than leave these tests
    passing against fields that no longer exist."""
    for fields, model in ((ENTRY_FIELDS, HseEntry), (SCHEDULE_FIELDS, HseSchedule)):
        columns = {c.key for c in model.__table__.columns}
        missing = [n for n in fields if n not in columns]
        assert not missing, (f'Stub reads non-columns on {model.__name__}: '
                             + ', '.join(missing))


# --- the period -----------------------------------------------------------

def test_a_month_compares_against_the_month_before():
    w = period('month', TODAY)
    assert (w['start'], w['end']) == (date(2026, 9, 1), date(2026, 9, 30))
    assert (w['prev_start'], w['prev_end']) == (date(2026, 8, 1), date(2026, 8, 31))
    assert w['label'] == 'September 2026'


def test_a_year_is_the_trailing_twelve_months_not_january_to_december():
    """A review in September should read the twelve months he actually
    worked, not eight months and a gap."""
    w = period('year', TODAY)
    assert (w['start'], w['end']) == (date(2025, 10, 1), date(2026, 9, 30))
    assert (w['prev_start'], w['prev_end']) == (date(2024, 10, 1), date(2025, 9, 30))
    assert w['label'] == 'Oct 2025 – Sep 2026'


def test_a_month_period_rolls_back_over_a_year_boundary():
    w = period('month', date(2026, 1, 20))
    assert (w['prev_start'], w['prev_end']) == (date(2025, 12, 1), date(2025, 12, 31))


def test_an_unknown_view_falls_back_to_the_month():
    assert period('decade', TODAY)['view'] == 'month'


def test_the_trend_runs_twelve_months_ending_with_the_period():
    months = trend_months(date(2026, 9, 30))
    assert len(months) == 12
    assert months[0]['start'] == date(2025, 10, 1)
    assert months[-1]['end'] == date(2026, 9, 30)
    assert [m['label'] for m in months][:3] == ['Oct', 'Nov', 'Dec']


# --- the tiles ------------------------------------------------------------

def _closed(day, severity='Medium', opened=None, **kw):
    return entry(entry_date=opened or day, closed_at=day, severity=severity,
                 status='Closed', **kw)


def test_a_falling_time_to_close_reads_as_an_improvement():
    """Lower is better here. An arrow that does not know that is worse than
    no arrow at all."""
    entries = [
        _closed(date(2026, 8, 21), opened=date(2026, 8, 1)),   # 20 days, prev
        _closed(date(2026, 9, 6), opened=date(2026, 9, 1)),    # 5 days, now
    ]
    speed = next(t for t in tiles([], entries, period('month', TODAY), TODAY)
                 if t['key'] == 'speed')
    assert speed['value'] == 5
    assert speed['delta'] == {'improved': True, 'from': 20}


def test_a_first_period_gets_no_arrow_rather_than_a_fake_one():
    entries = [_closed(date(2026, 9, 6), opened=date(2026, 9, 1))]
    speed = next(t for t in tiles([], entries, period('month', TODAY), TODAY)
                 if t['key'] == 'speed')
    assert speed['delta'] is None


def test_a_rising_on_time_rate_reads_as_an_improvement():
    late = _closed(date(2026, 8, 30), opened=date(2026, 8, 1))     # 29d vs 15
    quick = _closed(date(2026, 9, 5), opened=date(2026, 9, 1))     # 4d vs 15
    on_time = next(t for t in tiles([], [late, quick], period('month', TODAY), TODAY)
                   if t['key'] == 'on_time')
    assert on_time['value'] == 100
    assert on_time['delta'] == {'improved': True, 'from': 0}


def test_the_average_names_how_much_of_it_was_someone_elses_delay():
    parked = _closed(date(2026, 9, 20), opened=date(2026, 9, 1),
                     waiting_on_id=3, waiting_since=date(2026, 9, 5))
    speed = next(t for t in tiles([], [parked], period('month', TODAY), TODAY)
                 if t['key'] == 'speed')
    assert speed['detail'] == '1 of them waiting on others'


def test_an_empty_period_gives_dashes_not_zeroes():
    """Nothing closed is not a 0% on-time rate, and the tile must not imply
    one."""
    for tile in tiles([], [], period('month', TODAY), TODAY):
        if tile['key'] in ('on_time', 'speed', 'coverage'):
            assert tile['value'] is None


def test_the_coverage_tile_reads_the_engine_rather_than_recounting():
    from app.modules.hse.lib.schedule import coverage

    walk = sched(frequency='weekly', weekday=0, starts_on=date(2026, 9, 1))
    window = period('month', TODAY)
    tile = next(t for t in tiles([walk], [], window, TODAY) if t['key'] == 'coverage')
    engine = coverage([walk], [], window['start'], window['end'], TODAY)
    assert tile['value'] == engine['percent']
    assert tile['detail'] == f"{engine['done']} of {engine['due']} planned"


# --- the charts -----------------------------------------------------------

def test_the_bars_and_the_tile_come_from_the_same_coverage():
    walk = sched(frequency='weekly', weekday=0, starts_on=date(2026, 1, 1))
    window = period('year', TODAY)
    months = trend_months(window['end'])
    series = coverage_series([walk], [], months, TODAY)
    assert len(series) == 12
    assert sum(row['planned'] for row in series) > 0
    assert all(row['done'] == 0 for row in series)


def test_a_month_with_nothing_closed_breaks_the_line_rather_than_dropping_to_zero():
    """Nothing closed is not an instant turnaround, and a line through zero
    would say it was."""
    months = trend_months(date(2026, 9, 30))
    entries = [_closed(date(2026, 9, 6), opened=date(2026, 9, 1))]
    series = age_series(entries, months)
    assert series[-1]['days'] == 5
    assert series[0]['days'] is None

    drawn = charts.line(series)
    assert drawn['points'][0]['y'] is None
    # One run of real points, so nothing is drawn across the empty months.
    assert len(drawn['paths']) == 0
    assert drawn['first']['days'] == 5


def test_the_line_joins_consecutive_months_and_splits_at_a_gap():
    series = [{'label': 'Jan', 'days': 10}, {'label': 'Feb', 'days': 12},
              {'label': 'Mar', 'days': None}, {'label': 'Apr', 'days': 8},
              {'label': 'May', 'days': 6}]
    drawn = charts.line(series)
    assert len(drawn['paths']) == 2


def test_bars_never_overflow_their_chart():
    series = [{'label': 'Jan', 'planned': 7, 'done': 3}]
    drawn = charts.grouped_bars(series, height=168)
    for bar in drawn['bars']:
        assert bar['y'] >= 0
        assert bar['y'] + bar['h'] <= drawn['floor'] + 0.1


def test_an_empty_chart_still_draws_its_gridlines():
    drawn = charts.grouped_bars([{'label': 'Jan', 'planned': 0, 'done': 0}])
    assert len(drawn['gridlines']) == 3
    assert all(bar['h'] == 0 for bar in drawn['bars'])


# --- the panels -----------------------------------------------------------

def test_small_counts_do_not_repeat_gridline_labels():
    # A month topping out at 1 or 2 must not round three even gridlines into
    # duplicates like 0, 1, 1 — the officer's metrics are mostly low counts.
    for top in (1, 2, 3):
        drawn = charts.grouped_bars(
            [{'label': 'Jan', 'planned': top, 'done': 0}])
        labels = [g['value'] for g in drawn['gridlines']]
        assert labels == sorted(set(labels)), f'duplicate gridlines at top={top}: {labels}'
        assert all(v > 0 for v in labels)


def test_the_near_miss_note_has_a_number_behind_it():
    entries = [
        entry(id=1, entry_date=date(2026, 9, 2), data={'event_class': 'Near miss'}),
        entry(id=2, entry_date=date(2026, 9, 3), data={'event_class': 'Near miss'}),
        entry(id=3, entry_date=date(2026, 9, 4), data={'event_class': 'Incident'}),
        entry(id=4, entry_date=date(2026, 9, 5)),
    ]
    row = reporting(entries, period('month', TODAY))
    assert row['ratio'] == 2.0
    assert row['unclassified'] == 1


def test_a_renewal_filed_before_expiry_counts_as_on_time():
    old = entry(id=1, register='compliance_renewal', ref='COM-0001',
                entry_date=date(2025, 9, 1), due_at=date(2026, 9, 1),
                compliance_item_id=1)
    new = entry(id=2, register='compliance_renewal', ref='COM-0009',
                entry_date=date(2026, 8, 20), due_at=date(2027, 8, 20),
                compliance_item_id=1)
    panel = compliance_panel([old, new], period('year', TODAY), TODAY)
    assert panel['renewals'] == {'renewed': 1, 'on_time': 1}


def test_a_renewal_filed_after_expiry_is_counted_but_not_as_on_time():
    old = entry(id=1, register='compliance_renewal', ref='COM-0001',
                entry_date=date(2025, 9, 1), due_at=date(2026, 3, 1),
                compliance_item_id=2)
    new = entry(id=2, register='compliance_renewal', ref='COM-0009',
                entry_date=date(2026, 4, 2), due_at=date(2027, 4, 2),
                compliance_item_id=2)
    panel = compliance_panel([old, new], period('year', TODAY), TODAY)
    assert panel['renewals'] == {'renewed': 1, 'on_time': 0}


def test_renaming_a_certificate_keeps_its_renewal_history():
    """The whole point of the reference: the two entries carry different
    display names — as if the item were renamed between filings — but the
    same id, so they still count as one certificate's renewal, not two new
    items."""
    cert = _Ref(3, 'ISO 45001:2018')
    old = entry(id=1, register='compliance_renewal', ref='COM-0001',
                entry_date=date(2025, 9, 1), due_at=date(2026, 9, 1),
                compliance_item_id=3, compliance_item=_Ref(3, 'ISO 45001'))
    new = entry(id=2, register='compliance_renewal', ref='COM-0009',
                entry_date=date(2026, 8, 20), due_at=date(2027, 8, 20),
                compliance_item_id=3, compliance_item=cert)
    panel = compliance_panel([old, new], period('year', TODAY), TODAY)
    assert panel['renewals'] == {'renewed': 1, 'on_time': 1}


def test_a_certificate_with_none_set_is_skipped_not_grouped():
    """Two entries with no certificate must not collapse into one group and
    invent a renewal between unrelated rows."""
    a = entry(id=1, register='compliance_renewal', ref='COM-0001',
              entry_date=date(2025, 9, 1), due_at=date(2026, 9, 1),
              compliance_item_id=None)
    b = entry(id=2, register='compliance_renewal', ref='COM-0009',
              entry_date=date(2026, 8, 20), due_at=date(2027, 8, 20),
              compliance_item_id=None)
    panel = compliance_panel([a, b], period('year', TODAY), TODAY)
    assert panel['renewals'] == {'renewed': 0, 'on_time': 0}


def test_what_lapsed_is_named_rather_than_hidden():
    lapsed = entry(id=1, register='compliance_renewal', ref='COM-0003',
                   entry_date=date(2025, 6, 1), due_at=date(2026, 6, 1),
                   compliance_item_id=4,
                   compliance_item=_Ref(4, 'Forklift licence'))
    panel = compliance_panel([lapsed], period('year', TODAY), TODAY)
    assert panel['lapsed_count'] == 1
    assert panel['lapsed'][0]['item'] == 'Forklift licence'


def test_open_actions_land_in_the_right_age_bucket():
    rows = [
        entry(id=1, entry_date=date(2026, 9, 11), status='Open'),      # 3 days
        entry(id=2, entry_date=date(2026, 9, 1), status='Open'),       # 13 days
        entry(id=3, entry_date=date(2026, 8, 1), status='Open'),       # 44 days
        entry(id=4, entry_date=date(2026, 1, 1), status='Open'),       # 256 days
    ]
    ageing = open_by_age(rows, TODAY)
    assert [b['count'] for b in ageing['buckets']] == [1, 1, 1, 1]
    assert ageing['total'] == 4


def test_a_log_has_no_open_actions_to_age():
    """A toolbox talk either happened or was never logged. It must not sit in
    the ageing panel forever."""
    talk = entry(id=1, register='toolbox_talk', entry_date=date(2026, 1, 1))
    assert open_by_age([talk], TODAY)['total'] == 0


def test_the_oldest_open_action_is_named_with_who_is_holding_it():
    old = entry(id=1, ref='INS-0001', entry_date=date(2026, 3, 2), status='Open',
                waiting_on_id=7, waiting_on=_Person('Site manager'))
    oldest = open_by_age([old], TODAY)['oldest']
    assert oldest['ref'] == 'INS-0001'
    assert oldest['waiting_on'] == 'Site manager'


def test_nothing_open_gives_no_oldest_rather_than_an_error():
    assert open_by_age([], TODAY)['oldest'] is None


# --- the report's sections ------------------------------------------------

def test_the_report_prints_the_sla_it_judges_against_worst_first():
    assert sla_table() == [('Critical', SLA_DAYS['Critical']),
                           ('High', SLA_DAYS['High']),
                           ('Medium', SLA_DAYS['Medium']),
                           ('Low', SLA_DAYS['Low'])]


def test_schedule_coverage_puts_the_worst_round_first():
    """One failing schedule must not be averaged away by the ones that went
    fine, so the weakest sorts to the top."""
    good = sched(id=1, label='Weekly walk', frequency='weekly', weekday=0,
                 starts_on=date(2026, 9, 1))
    bad = sched(id=2, label='Forklift check', frequency='weekly', weekday=1,
                starts_on=date(2026, 9, 1))
    done = [entry(id=9, register='general_inspection', schedule_id=1,
                  occurrence_date=date(2026, 9, 7), entry_date=date(2026, 9, 7)),
            entry(id=10, register='general_inspection', schedule_id=1,
                  occurrence_date=date(2026, 9, 14), entry_date=date(2026, 9, 14))]
    rows = schedule_coverage([good, bad], done, period('month', TODAY), TODAY)
    assert rows[0]['label'] == 'Forklift check'
    assert rows[0]['percent'] == 0


def test_expiring_next_lists_soonest_first_and_ignores_what_already_went():
    soon = entry(id=1, register='compliance_renewal', ref='COM-1',
                 entry_date=date(2026, 1, 1), due_at=date(2026, 9, 20),
                 data={'item': 'Insurance'})
    later = entry(id=2, register='compliance_renewal', ref='COM-2',
                  entry_date=date(2026, 1, 1), due_at=date(2026, 10, 10),
                  data={'item': 'Permit'})
    gone = entry(id=3, register='compliance_renewal', ref='COM-3',
                 entry_date=date(2026, 1, 1), due_at=date(2026, 8, 1),
                 data={'item': 'Old licence'})
    rows = expiring_next([later, gone, soon], TODAY)
    assert [r['ref'] for r in rows] == ['COM-1', 'COM-2']


def test_a_read_out_is_never_written_about_a_number_that_does_not_exist():
    """The closing notes come off the figures. With nothing recorded there is
    nothing to say, and the report says nothing rather than guessing."""
    window = period('month', TODAY)
    notes = read_outs(tiles([], [], window, TODAY),
                      reporting([], window),
                      compliance_panel([], window, TODAY),
                      open_by_age([], TODAY))
    assert notes == []


def test_a_completed_induction_is_not_an_open_action():
    """Its register has no closing date, so the panel has to read the status.
    Left alone, a finished training course would age forever."""
    done = entry(id=1, register='induction_training', ref='TRN-0001',
                 entry_date=date(2025, 10, 1), status='Completed')
    assert open_by_age([done], TODAY)['total'] == 0


def test_severity_with_nothing_closed_is_left_out_not_shown_as_zero():
    rows = closed_by_severity(
        [_closed(date(2026, 9, 5), 'High', opened=date(2026, 9, 1))],
        period('month', TODAY), TODAY)
    assert [r['label'] for r in rows] == ['High']
    assert rows[0] == {'label': 'High', 'closed': 1, 'on_time': 1, 'percent': 100}


def test_severity_rows_run_worst_first():
    entries = [_closed(date(2026, 9, 5), 'Low', opened=date(2026, 9, 1)),
               _closed(date(2026, 9, 6), 'Critical', opened=date(2026, 9, 1))]
    rows = closed_by_severity(entries, period('month', TODAY), TODAY)
    assert [r['label'] for r in rows] == ['Critical', 'Low']


# --- chart sizing ---------------------------------------------------------

def test_the_chart_is_sized_to_the_width_it_will_render_at():
    """The SVG scales everything inside it, type included. A chart drawn at
    556 and stretched across a 1160px card renders its 9px labels at 19px,
    which is why the screen and the report ask for different widths."""
    assert charts.PRINT_WIDTH < charts.SCREEN_WIDTH
    screen = charts.grouped_bars([{'label': 'Jan', 'planned': 4, 'done': 2}])
    report = charts.grouped_bars([{'label': 'Jan', 'planned': 4, 'done': 2}],
                                 width=charts.PRINT_WIDTH, height=230)
    assert screen['width'] == charts.SCREEN_WIDTH
    assert report['width'] == charts.PRINT_WIDTH
    # The bars scale with the chart rather than staying a fixed pixel size,
    # so neither surface ends up with hairlines or slabs.
    assert report['bars'][0]['w'] < screen['bars'][0]['w']


def test_bars_share_the_width_out_however_many_months_there_are():
    """Six months and twelve months both have to look deliberate."""
    six = charts.grouped_bars([{'label': str(i), 'planned': 2, 'done': 1}
                               for i in range(6)])
    twelve = charts.grouped_bars([{'label': str(i), 'planned': 2, 'done': 1}
                                  for i in range(12)])
    assert six['bars'][0]['w'] > twelve['bars'][0]['w']
    # Nothing runs off the right edge either way.
    for drawn in (six, twelve):
        last = drawn['bars'][-1]
        assert last['x'] + last['w'] <= drawn['width'] + 0.5
