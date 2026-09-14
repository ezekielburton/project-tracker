"""The schedule engine: recurring obligations turned into occurrences,
computed at read time and never stored.

Plain stubs again rather than mapped models — instantiating a mapped class
configures every mapper in the app, which would make date arithmetic
depend on a database. The two stub guards below keep them honest.
"""
from datetime import date

from app.modules.hse.lib.schedule import (
    coverage, falls_due_on, next_due, occurrence_dates, occurrences,
    schedule_targets,
)
from app.modules.hse.models import HseEntry, HseSchedule


TODAY = date(2026, 9, 14)  # a Monday

SCHEDULE_FIELDS = ('id', 'register', 'label', 'frequency', 'interval',
                   'weekday', 'day_of_month', 'starts_on', 'ends_on', 'active')
ENTRY_FIELDS = ('id', 'register', 'schedule_id', 'occurrence_date',
                'asset_id', 'entry_date')


class _Asset:
    def __init__(self, id, label='Asset', active=True):
        self.id, self.label, self.active = id, label, active


class _Schedule:
    """Stands in for an HseSchedule. `assets` is a relationship rather than
    a column, so it sits outside the guarded field list."""

    def __init__(self, assets=None, **kw):
        for name in SCHEDULE_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'
        self.assets = assets or []


class _Entry:
    def __init__(self, **kw):
        for name in ENTRY_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'
        self.asset = None


def sched(**kw):
    kw.setdefault('id', 1)
    kw.setdefault('register', 'general_inspection')
    kw.setdefault('label', 'Vehicle inspection')
    kw.setdefault('interval', 1)
    kw.setdefault('active', True)
    return _Schedule(**kw)


def entry(**kw):
    kw.setdefault('register', 'general_inspection')
    return _Entry(**kw)


def test_the_stubs_only_use_real_columns():
    """A column rename must break the stubs here rather than leave these
    tests passing against fields that no longer exist."""
    for stub_fields, model in ((SCHEDULE_FIELDS, HseSchedule),
                               (ENTRY_FIELDS, HseEntry)):
        columns = {c.key for c in model.__table__.columns}
        missing = [n for n in stub_fields if n not in columns]
        assert not missing, (
            f'The stub reads fields that are not columns on '
            f'{model.__name__}: ' + ', '.join(missing)
        )


# --- generating the dates -------------------------------------------------

def test_weekly_lands_on_the_chosen_weekday():
    s = sched(frequency='weekly', weekday=0, starts_on=date(2026, 9, 1))
    assert occurrence_dates(s, date(2026, 9, 1), date(2026, 9, 30)) == [
        date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28)]


def test_dates_are_anchored_to_the_schedule_not_the_window():
    """The same schedule must give the same dates whether the page renders
    one month or a whole year — otherwise a tile could be planned in one
    view and absent in another."""
    s = sched(frequency='weekly', weekday=0, starts_on=date(2026, 9, 1))
    month = occurrence_dates(s, date(2026, 9, 1), date(2026, 9, 30))
    year = occurrence_dates(s, date(2026, 1, 1), date(2026, 12, 31))
    assert [d for d in year if d.month == 9] == month


def test_an_interval_spaces_the_weeks_out():
    s = sched(frequency='weekly', weekday=2, interval=2, starts_on=date(2026, 9, 1))
    assert occurrence_dates(s, date(2026, 9, 1), date(2026, 10, 15)) == [
        date(2026, 9, 2), date(2026, 9, 16), date(2026, 9, 30), date(2026, 10, 14)]


def test_daily_with_an_interval():
    s = sched(frequency='daily', interval=3, starts_on=date(2026, 9, 10))
    assert occurrence_dates(s, date(2026, 9, 10), date(2026, 9, 20)) == [
        date(2026, 9, 10), date(2026, 9, 13), date(2026, 9, 16), date(2026, 9, 19)]


def test_a_monthly_day_clamps_to_short_months():
    """The 31st of February is the 28th, not a month with no inspection."""
    s = sched(frequency='monthly', day_of_month=31, starts_on=date(2026, 1, 1))
    assert occurrence_dates(s, date(2026, 1, 1), date(2026, 4, 30)) == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_quarterly_and_annual():
    q = sched(frequency='quarterly', starts_on=date(2026, 2, 10))
    assert occurrence_dates(q, date(2026, 1, 1), date(2026, 12, 31)) == [
        date(2026, 2, 10), date(2026, 5, 10), date(2026, 8, 10), date(2026, 11, 10)]

    a = sched(frequency='annual', starts_on=date(2026, 6, 30))
    assert occurrence_dates(a, date(2026, 1, 1), date(2029, 1, 1)) == [
        date(2026, 6, 30), date(2027, 6, 30), date(2028, 6, 30)]


def test_a_six_monthly_service_is_monthly_with_an_interval():
    s = sched(frequency='monthly', interval=6, starts_on=date(2026, 3, 5))
    assert occurrence_dates(s, date(2026, 1, 1), date(2027, 12, 31)) == [
        date(2026, 3, 5), date(2026, 9, 5), date(2027, 3, 5), date(2027, 9, 5)]


def test_nothing_falls_outside_starts_on_and_ends_on():
    s = sched(frequency='weekly', weekday=0, starts_on=date(2026, 9, 14),
              ends_on=date(2026, 9, 28))
    assert occurrence_dates(s, date(2026, 8, 1), date(2026, 12, 31)) == [
        date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28)]


def test_a_deactivated_schedule_generates_nothing():
    s = sched(frequency='weekly', weekday=0, starts_on=date(2026, 9, 1), active=False)
    assert occurrence_dates(s, date(2026, 9, 1), date(2026, 9, 30)) == []


def test_an_unknown_frequency_is_due_never_not_every_day():
    s = sched(frequency='whenever', starts_on=date(2026, 9, 1))
    assert occurrence_dates(s, date(2026, 9, 1), date(2026, 12, 31)) == []


def test_a_zero_interval_cannot_stall_the_generator():
    s = sched(frequency='daily', interval=0, starts_on=date(2026, 9, 12))
    assert occurrence_dates(s, date(2026, 9, 12), date(2026, 9, 14)) == [
        date(2026, 9, 12), date(2026, 9, 13), date(2026, 9, 14)]


# --- what one occurrence covers -------------------------------------------

def test_a_schedule_without_assets_is_due_once():
    """A tool box talk is one obligation, not one per vehicle."""
    assert schedule_targets(sched(frequency='weekly', starts_on=TODAY)) == [None]


def test_a_schedule_with_assets_is_due_once_per_asset():
    a, b = _Asset(11), _Asset(12)
    s = sched(frequency='weekly', starts_on=TODAY, assets=[a, b])
    assert schedule_targets(s) == [a, b]


def test_a_retired_asset_stops_being_due():
    live, gone = _Asset(11), _Asset(13, active=False)
    s = sched(frequency='weekly', starts_on=TODAY, assets=[live, gone])
    assert schedule_targets(s) == [live]


def test_a_schedule_whose_assets_all_retired_is_due_for_nothing():
    """It must not quietly become a general obligation the officer never
    set up."""
    s = sched(frequency='weekly', starts_on=TODAY, assets=[_Asset(13, active=False)])
    assert schedule_targets(s) == []
    assert occurrences([s], [], TODAY, TODAY, TODAY) == []


# --- states ---------------------------------------------------------------

def _vehicles():
    return sched(id=5, frequency='weekly', weekday=0, starts_on=date(2026, 9, 1),
                 assets=[_Asset(11, 'D-55831'), _Asset(12, 'GMC Sierra')])


def test_planned_overdue_and_today():
    occ = occurrences([_vehicles()], [], date(2026, 9, 7), date(2026, 9, 21), TODAY)
    state = {o['date']: o['state'] for o in occ}
    assert state[date(2026, 9, 7)] == 'overdue'
    assert state[date(2026, 9, 14)] == 'planned'   # due today is not yet missed
    assert state[date(2026, 9, 21)] == 'planned'
    assert occ[0]['due'] == 2                      # one per vehicle


def test_a_late_entry_still_ticks_off_its_occurrence():
    """Monday's inspection done on Wednesday: the occurrence reads done,
    and nothing is back-dated — the entry keeps its real date."""
    filed = [entry(id=1, schedule_id=5, occurrence_date=date(2026, 9, 7),
                   asset_id=11, entry_date=date(2026, 9, 9)),
             entry(id=2, schedule_id=5, occurrence_date=date(2026, 9, 7),
                   asset_id=12, entry_date=date(2026, 9, 9))]
    occ = occurrences([_vehicles()], filed, date(2026, 9, 7), date(2026, 9, 7), TODAY)
    assert occ[0]['state'] == 'done'


def test_a_half_finished_occurrence_is_still_outstanding():
    filed = [entry(id=1, schedule_id=5, occurrence_date=date(2026, 9, 7), asset_id=11)]
    occ = occurrences([_vehicles()], filed, date(2026, 9, 7), date(2026, 9, 7), TODAY)
    assert occ[0]['state'] == 'overdue'
    assert (occ[0]['done'], occ[0]['due']) == (1, 2)


def test_work_filed_against_a_since_retired_asset_still_shows():
    """He did the inspection. Retiring the vehicle later must not erase it
    from the day he did it."""
    filed = [entry(id=3, schedule_id=5, occurrence_date=date(2026, 9, 7), asset_id=99)]
    occ = occurrences([_vehicles()], filed, date(2026, 9, 7), date(2026, 9, 7), TODAY)
    assert len(occ[0]['items']) == 3


def test_unplanned_work_ticks_nothing_off():
    """An entry filed straight into the register is real work, but it is
    not evidence that a planned inspection happened."""
    filed = [entry(id=4, schedule_id=None, occurrence_date=None, asset_id=11)]
    occ = occurrences([_vehicles()], filed, date(2026, 9, 7), date(2026, 9, 7), TODAY)
    assert occ[0]['done'] == 0


# --- coverage -------------------------------------------------------------

def test_coverage_ignores_what_is_not_due_yet():
    """Due on the 7th and the 14th, two vehicles each. The 21st is still
    ahead and must not count against him."""
    filed = [entry(id=1, schedule_id=5, occurrence_date=date(2026, 9, 7), asset_id=11),
             entry(id=2, schedule_id=5, occurrence_date=date(2026, 9, 7), asset_id=12)]
    cov = coverage([_vehicles()], filed, date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert cov == {'due': 4, 'done': 2, 'outstanding': 2, 'percent': 50}


def test_coverage_is_unknown_rather_than_zero_when_nothing_was_due():
    cov = coverage([], [], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert cov['due'] == 0
    assert cov['percent'] is None


# --- next due -------------------------------------------------------------

def test_next_due_is_the_next_date_from_today():
    assert next_due(_vehicles(), TODAY) == date(2026, 9, 14)


# --- the write-path guard -------------------------------------------------

def test_falls_due_on_accepts_only_real_occurrence_dates():
    """The entry route checks this before stamping an occurrence onto an
    entry. Without it a hand-made request could tick off work that was
    never planned, and coverage stops meaning anything."""
    s = _vehicles()
    assert falls_due_on(s, date(2026, 9, 14)) is True    # a Monday in range
    assert falls_due_on(s, date(2026, 9, 15)) is False   # the Tuesday after
    assert falls_due_on(s, date(2026, 8, 31)) is False   # before it starts


def test_falls_due_on_refuses_a_date_past_the_end():
    s = sched(frequency='weekly', weekday=0, starts_on=date(2026, 1, 1),
              ends_on=date(2026, 6, 1))
    assert falls_due_on(s, date(2026, 5, 25)) is True
    assert falls_due_on(s, date(2026, 6, 8)) is False


def test_falls_due_on_refuses_a_retired_schedule():
    s = sched(frequency='weekly', weekday=0, starts_on=date(2026, 9, 1),
              active=False)
    assert falls_due_on(s, date(2026, 9, 14)) is False


def test_an_ended_schedule_has_no_next_due():
    s = sched(frequency='weekly', weekday=0, starts_on=date(2026, 1, 1),
              ends_on=date(2026, 6, 1))
    assert next_due(s, TODAY) is None
