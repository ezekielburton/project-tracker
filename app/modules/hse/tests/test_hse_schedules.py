"""What a recurring obligation is allowed to say.

Validation in lib/schedules.py is pure on purpose — no database, no mapped
model — so every rule here runs without the app fixture, and the preview
the officer sees is produced by the same code that accepts the save.
"""
from datetime import date

import pytest

from app.modules.hse.lib.registers import HSE_REGISTERS, asset_field, schedulable_registers
from app.modules.hse.lib.schedules import (
    MAX_INTERVAL, ValidationError, applies_to_text, cadence_short, cadence_text,
    clean_payload, due_status, form_options, plan_from, preview_dates,
)
from app.modules.hse.models import HseSchedule


TODAY = date(2026, 9, 14)  # a Monday

# Assets the form is allowed to offer, standing in for the active fleet.
AVAILABLE = (11, 12, 13)


def payload(**kw):
    """A valid weekly vehicle inspection, unless a test breaks one part."""
    base = {
        'label': 'Weekly vehicle inspection',
        'register': 'vehicle_inspection',
        'frequency': 'weekly',
        'interval': 1,
        'weekday': 0,
        'starts_on': '2026-09-01',
        'asset_ids': [11, 12],
    }
    base.update(kw)
    return base


def clean(**kw):
    return clean_payload(payload(**kw), AVAILABLE)


def errors_from(**kw):
    with pytest.raises(ValidationError) as caught:
        clean(**kw)
    return caught.value.errors


# --- the declaration ------------------------------------------------------

def test_the_stub_free_fields_are_real_columns():
    """clean_payload returns a dict written straight onto HseSchedule, so a
    renamed column must fail here rather than at the first save."""
    values, _ = clean()
    columns = {c.key for c in HseSchedule.__table__.columns}
    missing = [name for name in values if name not in columns]
    assert not missing, 'clean_payload returns keys that are not columns: ' + ', '.join(missing)


def test_only_recurring_registers_are_offered():
    offered = {r['key'] for r in form_options()['registers']}
    assert offered == {reg.key for reg in schedulable_registers()}
    # The two the workbook says have no calendar due date.
    assert 'vehicle_service' not in offered
    assert 'machine_preventive' not in offered


def test_a_register_that_cannot_recur_is_refused():
    assert 'register' in errors_from(register='vehicle_service', asset_ids=[])
    assert 'register' in errors_from(register='nonsense', asset_ids=[])


# --- the basics -----------------------------------------------------------

def test_a_valid_form_survives_intact():
    values, assets = clean()
    assert values['label'] == 'Weekly vehicle inspection'
    assert values['register'] == 'vehicle_inspection'
    assert values['frequency'] == 'weekly'
    assert values['weekday'] == 0
    assert values['starts_on'] == date(2026, 9, 1)
    assert values['ends_on'] is None
    assert assets == [11, 12]


def test_a_name_is_required():
    assert 'label' in errors_from(label='   ')


def test_an_interval_must_be_sane():
    assert 'interval' in errors_from(interval=0)
    assert 'interval' in errors_from(interval=MAX_INTERVAL + 1)
    assert 'interval' in errors_from(interval='often')


def test_a_start_date_is_required_and_must_be_a_date():
    assert 'starts_on' in errors_from(starts_on='')
    assert 'starts_on' in errors_from(starts_on='next tuesday')


def test_it_cannot_end_before_it_starts():
    assert 'ends_on' in errors_from(starts_on='2026-09-01', ends_on='2026-08-01')
    values, _ = clean(ends_on='2026-12-31')
    assert values['ends_on'] == date(2026, 12, 31)


def test_a_duplicate_asset_is_counted_once():
    _, assets = clean(asset_ids=[11, 11, 12])
    assert assets == [11, 12]


def test_an_asset_that_is_no_longer_available_is_refused():
    assert 'asset_ids' in errors_from(asset_ids=[11, 99])


# --- the sub-fields that depend on frequency ------------------------------

def test_a_weekday_only_applies_to_a_weekly_schedule():
    values, _ = clean(frequency='monthly', day_of_month=15, weekday=3)
    assert values['weekday'] is None
    assert values['day_of_month'] == 15


def test_a_day_of_month_only_applies_to_the_monthly_family():
    values, _ = clean(frequency='weekly', weekday=2, day_of_month=15)
    assert values['day_of_month'] is None
    assert values['weekday'] == 2


def test_an_omitted_weekday_is_allowed():
    """The generator falls back to the start date's own weekday, so leaving
    it blank is a real choice rather than an error."""
    values, _ = clean(weekday='')
    assert values['weekday'] is None


def test_out_of_range_weekday_and_day_are_refused():
    assert 'weekday' in errors_from(weekday=9)
    assert 'day_of_month' in errors_from(frequency='monthly', day_of_month=41)


# --- the asset rule -------------------------------------------------------

def test_a_register_that_needs_an_asset_needs_one_on_the_schedule():
    """Otherwise "Log it" opens a form it cannot satisfy."""
    assert asset_field(_register('vehicle_inspection')).required is True
    assert 'asset_ids' in errors_from(asset_ids=[])


def test_a_register_with_no_asset_field_may_not_carry_assets():
    assert 'asset_ids' in errors_from(register='toolbox_talk', asset_ids=[11])
    values, assets = clean(register='toolbox_talk', asset_ids=[])
    assert values['register'] == 'toolbox_talk'
    assert assets == []


def test_the_preview_ignores_the_asset_rules():
    """Which assets are picked never changes the dates, and refusing to
    preview until the asset list is right would hide the one mistake the
    preview exists to catch."""
    values, _ = clean_payload(payload(asset_ids=[]), AVAILABLE, check_assets=False)
    assert values['frequency'] == 'weekly'


def _register(key):
    for reg in HSE_REGISTERS:
        if reg.key == key:
            return reg
    raise AssertionError(key)


# --- the preview ----------------------------------------------------------

def test_the_preview_shows_the_next_dates_from_today():
    values, _ = clean(starts_on='2026-09-01', weekday=0)
    assert preview_dates(values, today=TODAY) == [
        date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28),
        date(2026, 10, 5), date(2026, 10, 12)]


def test_a_schedule_starting_later_previews_from_its_start():
    values, _ = clean(starts_on='2027-01-04', weekday=0)
    assert preview_dates(values, today=TODAY)[0] == date(2027, 1, 4)


def test_the_preview_catches_weeks_typed_where_months_were_meant():
    """The whole reason it exists: two forms that differ by one dropdown
    produce visibly different dates."""
    weekly, _ = clean(frequency='weekly', interval=2, weekday=0, starts_on='2026-09-01')
    monthly, _ = clean(frequency='monthly', interval=2, starts_on='2026-09-01',
                       day_of_month=1)
    # Fortnightly from the first Monday on/after 1 Sep: 21 Sep, then 5 Oct.
    assert preview_dates(weekly, today=TODAY)[:2] == [date(2026, 9, 21), date(2026, 10, 5)]
    # Every two months from 1 Sep: 1 Nov, then 1 Jan.
    assert preview_dates(monthly, today=TODAY)[:2] == [date(2026, 11, 1), date(2027, 1, 1)]


def test_a_finished_schedule_previews_nothing():
    values, _ = clean(starts_on='2026-01-01', ends_on='2026-06-01')
    assert preview_dates(values, today=TODAY) == []


def test_plan_from_feeds_the_generator_without_a_model():
    values, _ = clean()
    plan = plan_from(values)
    assert plan.active is True
    assert plan.assets == ()


# --- how it reads ---------------------------------------------------------

class _Asset:
    def __init__(self, id, label='Asset', active=True, kind='vehicle', ref=None):
        self.id, self.label, self.active = id, label, active
        self.kind, self.ref = kind, ref


class _Sched:
    """Stands in for an HseSchedule. The generator and these helpers only
    read attributes, so nothing here needs the app fixture."""

    def __init__(self, assets=None, **kw):
        for name in ('id', 'register', 'label', 'frequency', 'interval', 'weekday',
                     'day_of_month', 'starts_on', 'ends_on'):
            setattr(self, name, kw.get(name))
        self.active = kw.get('active', True)
        self.assets = assets or []


class _Filed:
    """An entry already filed against an occurrence."""

    def __init__(self, schedule_id, occurrence_date, asset_id):
        self.id = 1
        self.schedule_id = schedule_id
        self.occurrence_date = occurrence_date
        self.asset_id = asset_id


def vehicles():
    """The fixture the due-date tests share: weekly on Mondays, two
    vehicles, running since the start of September."""
    return _Sched(id=5, register='vehicle_inspection', label='Vehicle inspection',
                  frequency='weekly', interval=1, weekday=0,
                  starts_on=date(2026, 9, 1),
                  assets=[_Asset(11, 'GMC Sierra'), _Asset(12, 'Toyota Hilux')])


def test_cadence_reads_the_way_he_would_say_it():
    assert cadence_text(_Sched(frequency='weekly', interval=1, weekday=0)) == 'Every Monday'
    assert cadence_text(_Sched(frequency='weekly', interval=2, weekday=2)) == \
        'Every 2 weeks on Wednesday'
    assert cadence_text(_Sched(frequency='daily', interval=1)) == 'Every day'
    assert cadence_text(_Sched(frequency='daily', interval=3)) == 'Every 3 days'
    assert cadence_text(_Sched(frequency='monthly', interval=1, day_of_month=15)) == \
        'Every month on the 15th'
    assert cadence_text(_Sched(frequency='monthly', interval=6, day_of_month=1)) == \
        'Every 6 months on the 1st'
    assert cadence_text(_Sched(frequency='annual', interval=1, day_of_month=22)) == \
        'Every year on the 22nd'


def test_cadence_falls_back_to_the_start_date_like_the_generator_does():
    """The sentence must not claim a different day from the dates."""
    sched = _Sched(frequency='weekly', interval=1, starts_on=date(2026, 9, 2))
    assert cadence_text(sched) == 'Every Wednesday'


def test_the_short_cadence_says_the_same_thing_in_less_room():
    """The table uses it and the calendar cards use the sentence form. Both
    read the same fields as the generator, so neither can claim a day the
    other does not."""
    assert cadence_short(_Sched(frequency='weekly', interval=1, weekday=0)) == 'Weekly · Mon'
    assert cadence_short(_Sched(frequency='weekly', interval=2, weekday=2)) == \
        'Every 2 weeks · Wed'
    assert cadence_short(_Sched(frequency='daily', interval=1)) == 'Daily'
    assert cadence_short(_Sched(frequency='monthly', interval=1, day_of_month=15)) == \
        'Monthly · 15th'
    assert cadence_short(_Sched(frequency='monthly', interval=6, day_of_month=5)) == \
        'Every 6 months · 5th'
    assert cadence_short(_Sched(frequency='annual', interval=1, day_of_month=22)) == \
        'Annual · 22nd'


def test_the_short_cadence_also_falls_back_to_the_start_date():
    assert cadence_short(_Sched(frequency='weekly', interval=1,
                                starts_on=date(2026, 9, 2))) == 'Weekly · Wed'


# --- what a schedule covers, in a few words -------------------------------

def test_a_schedule_with_no_assets_reads_as_site_wide():
    assert applies_to_text(_Sched(frequency='weekly', starts_on=TODAY)) == 'Site-wide'


def test_one_or_two_assets_are_named():
    s = _Sched(frequency='weekly', starts_on=TODAY, assets=[
        _Asset(11, 'GMC Sierra', ref='D-55831'),
        _Asset(12, 'Toyota Hilux', ref='D-41207'),
    ])
    assert applies_to_text(s) == 'D-55831, D-41207'


def test_more_than_two_collapse_to_a_count_of_their_kind():
    """A list of every plate is unreadable at four and useless at twelve."""
    s = _Sched(frequency='weekly', starts_on=TODAY,
               assets=[_Asset(i, 'Vehicle %d' % i, ref='D-%d' % i) for i in range(11, 15)])
    assert applies_to_text(s) == '4 vehicles'


def test_a_mixed_bag_is_counted_as_assets():
    s = _Sched(frequency='weekly', starts_on=TODAY, assets=[
        _Asset(11, 'Truck', kind='vehicle'),
        _Asset(12, 'Lathe', kind='machine'),
        _Asset(13, 'Forklift', kind='forklift'),
    ])
    assert applies_to_text(s) == '3 assets'


def test_a_schedule_whose_assets_all_retired_says_so():
    """Rather than naming things that no longer exist."""
    s = _Sched(frequency='weekly', starts_on=TODAY,
               assets=[_Asset(13, 'Old van', active=False)])
    assert applies_to_text(s) == 'Nothing active'


# --- what the Next due column actually means ------------------------------

def test_next_due_shows_what_he_owes_not_the_next_convenient_date():
    """Monday's inspection was never done, so Monday is what the column
    says. Showing next Monday instead would hide it behind a date that
    looks fine."""
    status = due_status(vehicles(), [], TODAY)
    assert status['date'] == date(2026, 9, 7)
    assert status['label'] == '7d overdue'
    assert status['overdue_days'] == 7


def test_next_due_shows_the_upcoming_date_once_nothing_is_outstanding():
    filed = [_Filed(5, date(2026, 9, 7), 11), _Filed(5, date(2026, 9, 7), 12)]
    status = due_status(vehicles(), filed, TODAY)
    assert status['date'] == TODAY
    assert status['label'] == 'Today'
    assert status['overdue_days'] == 0


def test_next_due_counts_the_days_ahead():
    s = _Sched(id=7, frequency='weekly', weekday=0, starts_on=date(2026, 9, 21))
    status = due_status(s, [], TODAY)
    assert status['date'] == date(2026, 9, 21)
    assert status['label'] == '7d'


def test_a_retired_schedule_is_due_for_nothing():
    s = _Sched(frequency='weekly', weekday=0, starts_on=date(2026, 9, 1), active=False)
    assert due_status(s, [], TODAY) == {'date': None, 'label': None, 'overdue_days': 0}


def test_the_lookback_stops_an_abandoned_schedule_reading_as_overdue_forever():
    """Something last due six years ago is not this week's problem."""
    s = _Sched(id=8, frequency='annual', starts_on=date(2020, 1, 15),
               ends_on=date(2021, 1, 1))
    assert due_status(s, [], TODAY)['date'] is None
