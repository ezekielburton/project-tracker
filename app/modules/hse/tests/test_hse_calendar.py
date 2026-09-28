"""Calendar view model: occurrences, logged entries and expiries on one grid, each counted once.

Plain stubs: lib/calendar.py reads attributes and never queries, so no app fixture.
"""
from datetime import date, datetime

from app.modules.hse.lib.calendar import (
    LEGEND_ORDER, MAX_CHIPS_PER_DAY, STATES, agenda_groups, day_summary, drawer_cards,
    expiry_items, grid_bounds, items_by_day, kpis, logged_items, month_grid,
    occurrence_items, parse_day, parse_month, shadowed_keys, shift_month,
    state_chips,
)
from app.modules.hse.models import HseEntry, HseSchedule


TODAY = date(2026, 9, 14)  # a Monday

SCHEDULE_FIELDS = ('id', 'register', 'label', 'frequency', 'interval',
                   'weekday', 'day_of_month', 'starts_on', 'ends_on', 'active')
ENTRY_FIELDS = ('id', 'register', 'ref', 'entry_date', 'due_at',
                'schedule_id', 'occurrence_date', 'asset_id')


class _Asset:
    def __init__(self, id, label='D-55831', active=True):
        self.id, self.label, self.active = id, label, active


class _Ref:
    def __init__(self, id, label):
        self.id, self.label = id, label


class _Schedule:
    def __init__(self, assets=None, **kw):
        for name in SCHEDULE_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'
        self.assets = assets or []


class _User:
    def __init__(self, name):
        self.name = name


class _Entry:
    def __init__(self, data=None, asset=None, created_by=None, created_at=None,
                 compliance_item=None, **kw):
        for name in ENTRY_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'
        self.data = data or {}
        self.asset = asset
        self.created_by = created_by
        self.created_at = created_at
        self.compliance_item = compliance_item


def vehicles():
    return _Schedule(id=5, register='vehicle_inspection', label='Vehicle inspection',
                     frequency='weekly', interval=1, weekday=0, active=True,
                     starts_on=date(2026, 9, 1),
                     assets=[_Asset(11, 'D-55831'), _Asset(12, 'GMC Sierra')])


def test_the_stubs_only_use_real_columns():
    for fields, model in ((SCHEDULE_FIELDS, HseSchedule), (ENTRY_FIELDS, HseEntry)):
        columns = {c.key for c in model.__table__.columns}
        missing = [n for n in fields if n not in columns]
        assert not missing, f'{model.__name__}: ' + ', '.join(missing)


# --- the three sources ----------------------------------------------------

def test_an_occurrence_carries_its_state_and_its_per_asset_detail():
    items = occurrence_items([vehicles()], [], date(2026, 9, 7), date(2026, 9, 21), TODAY)
    by_day = {i['date']: i for i in items}
    assert by_day[date(2026, 9, 7)]['state'] == 'overdue'
    assert by_day[date(2026, 9, 14)]['state'] == 'planned'
    assert by_day[date(2026, 9, 7)]['detail'] == '0 of 2'
    assert len(by_day[date(2026, 9, 7)]['targets']) == 2


def test_a_single_target_occurrence_shows_no_count():
    """A single-target occurrence has no "x of y" detail."""
    talk = _Schedule(id=9, register='toolbox_talk', label='Tool box talk',
                     frequency='weekly', interval=1, weekday=2, active=True,
                     starts_on=date(2026, 9, 1))
    items = occurrence_items([talk], [], date(2026, 9, 14), date(2026, 9, 20), TODAY)
    assert items[0]['detail'] is None


def test_work_that_satisfies_an_occurrence_is_not_also_drawn_as_logged():
    """An entry filed against an occurrence is not also drawn as logged (no double count)."""
    filed = _Entry(id=1, register='vehicle_inspection', ref='VIN-0001',
                   entry_date=date(2026, 9, 14), schedule_id=5,
                   occurrence_date=date(2026, 9, 14), asset_id=11)
    assert logged_items([filed], date(2026, 9, 1), date(2026, 9, 30)) == []


def test_unplanned_work_is_drawn_as_logged():
    incident = _Entry(id=2, register='incidents', ref='INC-0009',
                      entry_date=date(2026, 9, 10))
    items = logged_items([incident], date(2026, 9, 1), date(2026, 9, 30))
    assert len(items) == 1
    assert items[0]['state'] == 'logged'
    assert items[0]['date'] == date(2026, 9, 10)
    assert items[0]['detail'] == 'INC-0009'


def test_an_expiry_is_drawn_on_the_day_it_runs_out_not_the_day_it_was_filed():
    """An expiring entry appears once, on its due date, not on its entry date."""
    cert = _Entry(id=3, register='compliance_renewal', ref='COM-0004',
                  entry_date=date(2026, 6, 1), due_at=date(2026, 9, 30),
                  compliance_item=_Ref(3, 'ISO 45001 Certification'))
    assert logged_items([cert], date(2026, 6, 1), date(2026, 9, 30)) == []
    items = expiry_items([cert], date(2026, 9, 1), date(2026, 9, 30))
    assert len(items) == 1
    assert items[0]['date'] == date(2026, 9, 30)
    assert items[0]['state'] == 'expiring'
    assert items[0]['label'] == 'ISO 45001 Certification'


def test_an_expiry_against_an_asset_names_the_asset():
    doc = _Entry(id=4, register='vehicle_reg_insurance', ref='VRI-0002',
                 entry_date=date(2026, 1, 1), due_at=date(2026, 9, 20),
                 asset_id=11, asset=_Asset(11, 'Hino C17131'),
                 data={'document_type': 'Insurance'})
    items = expiry_items([doc], date(2026, 9, 1), date(2026, 9, 30))
    assert 'Hino C17131' in items[0]['label']


# --- the grid -------------------------------------------------------------

def test_the_grid_starts_on_monday_and_overhangs_the_month():
    start, end = grid_bounds(2026, 9)
    assert start.weekday() == 0
    assert start <= date(2026, 9, 1)
    assert end >= date(2026, 9, 30)


def test_every_day_in_view_is_loaded_by_the_bounds():
    """grid_bounds covers the overhang days too, so the route loads every cell shown."""
    start, end = grid_bounds(2026, 9)
    weeks = month_grid({}, 2026, 9, TODAY)
    for week in weeks:
        for day in week:
            assert start <= day['date'] <= end


def test_a_day_shows_a_few_items_and_counts_the_rest():
    day = date(2026, 9, 10)
    entries = [_Entry(id=i, register='incidents', ref=f'INC-{i:04d}', entry_date=day)
               for i in range(1, 7)]
    grouped = items_by_day([], entries, day, day, TODAY)
    cell = next(d for week in month_grid(grouped, 2026, 9, TODAY) for d in week
                if d['date'] == day)
    assert cell['count'] == 6
    assert len(cell['shown']) == MAX_CHIPS_PER_DAY
    assert cell['more'] == 6 - MAX_CHIPS_PER_DAY


def test_the_worst_state_colours_the_day():
    """A cell's colour and first item come from its worst state (overdue beats logged)."""
    day = date(2026, 9, 7)
    incident = _Entry(id=1, register='incidents', ref='INC-0001', entry_date=day)
    grouped = items_by_day([vehicles()], [incident], day, day, TODAY)
    cell = next(d for week in month_grid(grouped, 2026, 9, TODAY) for d in week
                if d['date'] == day)
    assert cell['worst'] == 'overdue'
    assert cell['day_items'][0]['state'] == 'overdue'


def test_days_outside_the_month_are_marked():
    weeks = month_grid({}, 2026, 9, TODAY)
    assert any(not day['in_month'] for week in weeks for day in week)
    assert all(day['in_month'] for day in weeks[2])   # a fully-inside week


# --- filtering ------------------------------------------------------------

def test_a_state_filter_keeps_only_that_state():
    incident = _Entry(id=1, register='incidents', ref='INC-0001',
                      entry_date=date(2026, 9, 7))
    grouped = items_by_day([vehicles()], [incident],
                           date(2026, 9, 1), date(2026, 9, 30), TODAY, 'logged')
    states = {i['state'] for items in grouped.values() for i in items}
    assert states == {'logged'}


def test_an_unknown_state_is_ignored_rather_than_emptying_the_page():
    grouped = items_by_day([vehicles()], [],
                           date(2026, 9, 1), date(2026, 9, 30), TODAY, 'nonsense')
    assert grouped


def test_the_legend_shows_every_state_even_at_zero():
    """Zero-count states stay in the legend so it keeps a stable layout."""
    chips = state_chips({}, None)
    assert [c['value'] for c in chips] == list(LEGEND_ORDER)
    assert all(c['count'] == 0 for c in chips)


def test_the_legend_covers_every_state_the_grid_can_draw():
    """LEGEND_ORDER holds exactly the states in STATES."""
    assert set(LEGEND_ORDER) == set(STATES)


def test_the_legend_dots_match_the_grid():
    """Legend dots are filled for exactly the states the grid draws filled."""
    filled = {c['value'] for c in state_chips({}, None) if c['filled']}
    assert filled == {'overdue', 'done', 'logged'}


def test_clicking_the_active_state_clears_the_filter():
    """The active legend chip links back to no filter."""
    chips = {c['value']: c for c in state_chips({}, 'overdue')}
    assert chips['overdue']['active'] is True
    assert chips['overdue']['href_state'] is None
    assert chips['planned']['href_state'] == 'planned'


def test_legend_counts_describe_everything_in_view():
    incident = _Entry(id=1, register='incidents', ref='INC-0001',
                      entry_date=date(2026, 9, 7))
    grouped = items_by_day([vehicles()], [incident],
                           date(2026, 9, 1), date(2026, 9, 30), TODAY)
    chips = {c['label']: c['count'] for c in state_chips(grouped, None)}
    assert chips['Logged'] == 1
    assert chips['Overdue'] >= 1
    assert sum(chips.values()) == sum(len(v) for v in grouped.values())


# --- agenda ---------------------------------------------------------------

def test_the_agenda_lists_only_days_with_something_on_them():
    grouped = items_by_day([vehicles()], [], TODAY, date(2026, 10, 14), TODAY)
    groups = agenda_groups(grouped, TODAY)
    assert groups
    assert all(g['count'] for g in groups)
    assert [g['date'] for g in groups] == sorted(g['date'] for g in groups)


def test_the_agenda_stops_at_its_horizon():
    grouped = items_by_day([vehicles()], [], TODAY, date(2027, 1, 1), TODAY)
    groups = agenda_groups(grouped, TODAY, days_ahead=14)
    assert groups
    assert max(g['date'] for g in groups) <= date(2026, 9, 28)


# --- the header -----------------------------------------------------------

def test_the_header_reads_coverage_rather_than_recomputing_it():
    """Header due/done/overdue come from coverage(), matching the performance page."""
    filed = [
        _Entry(id=1, register='vehicle_inspection', ref='VIN-0001',
               entry_date=date(2026, 9, 7), schedule_id=5,
               occurrence_date=date(2026, 9, 7), asset_id=11),
        _Entry(id=2, register='vehicle_inspection', ref='VIN-0002',
               entry_date=date(2026, 9, 7), schedule_id=5,
               occurrence_date=date(2026, 9, 7), asset_id=12),
    ]
    head = kpis([vehicles()], filed, date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert head['due'] == 4
    assert head['done'] == 2
    assert head['overdue'] == 2
    assert head['percent'] == 50


def test_unplanned_work_is_counted_beside_coverage_not_inside_it():
    """Unplanned work has its own count and does not change coverage."""
    incident = _Entry(id=9, register='incidents', ref='INC-0009',
                      entry_date=date(2026, 9, 10))
    head = kpis([vehicles()], [incident], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert head['unplanned'] == 1
    assert head['due'] == 4          # unchanged by the incident
    assert head['done'] == 0


def test_coverage_reads_as_a_dash_not_zero_when_nothing_was_due():
    head = kpis([], [], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert head['due'] == 0
    assert head['percent'] is None


# --- the drawer, flattened ------------------------------------------------

def test_an_occurrence_becomes_one_card_per_asset():
    """A multi-asset occurrence becomes one drawer card per asset."""
    grouped = items_by_day([vehicles()], [], date(2026, 9, 21), date(2026, 9, 21), TODAY)
    cards = drawer_cards(grouped[date(2026, 9, 21)], TODAY)
    assert [c['title'] for c in cards] == ['D-55831', 'GMC Sierra']
    assert {c['state'] for c in cards} == {'planned'}
    assert all(c['subtitle'] == 'Vehicle inspection' for c in cards)


def test_an_overdue_card_says_how_late_it_is():
    grouped = items_by_day([vehicles()], [], date(2026, 9, 7), date(2026, 9, 7), TODAY)
    card = drawer_cards(grouped[date(2026, 9, 7)], TODAY)[0]
    assert card['state'] == 'overdue'
    assert card['meta'] == 'Was due 7 Sep · 7 days overdue'


def test_a_card_due_today_says_so():
    grouped = items_by_day([vehicles()], [], TODAY, TODAY, TODAY)
    card = drawer_cards(grouped[TODAY], TODAY)[0]
    assert card['meta'] == 'Every Monday · due today'


def test_a_done_card_says_who_filed_it_and_when():
    filed = _Entry(id=1, register='vehicle_inspection', ref='VIN-0001',
                   entry_date=TODAY, schedule_id=5, occurrence_date=TODAY,
                   asset_id=11, created_by=_User('M. Dube'),
                   created_at=datetime(2026, 9, 14, 8, 40))
    grouped = items_by_day([vehicles()], [filed], TODAY, TODAY, TODAY)
    cards = {c['title']: c for c in drawer_cards(grouped[TODAY], TODAY)}
    assert cards['D-55831']['state'] == 'done'
    assert cards['D-55831']['meta'] == 'Logged 08:40 by M. Dube'
    assert cards['D-55831']['ref'] == 'VIN-0001'
    # The one still outstanding is untouched by its neighbour being done.
    assert cards['GMC Sierra']['state'] == 'planned'


def test_a_logged_card_shows_the_entrys_own_time_when_it_has_one():
    timed = _Entry(id=2, register='incidents', ref='INC-0001', entry_date=TODAY,
                   data={'entry_time': '07:15'}, created_by=_User('M. Dube'),
                   created_at=datetime(2026, 9, 14, 11, 5))
    untimed = _Entry(id=3, register='incidents', ref='INC-0002', entry_date=TODAY,
                     created_by=_User('M. Dube'), created_at=datetime(2026, 9, 14, 11, 5))
    grouped = items_by_day([], [timed, untimed], TODAY, TODAY, TODAY)
    metas = {c['ref']: c['meta'] for c in drawer_cards(grouped[TODAY], TODAY)}
    assert metas['INC-0001'] == 'Logged 07:15 by M. Dube'
    assert metas['INC-0002'] == 'Logged 11:05 by M. Dube', 'falls back to the filing time'


def test_work_already_done_keeps_its_place_in_the_day():
    """Done cards stay in the day's drawer alongside outstanding ones."""
    filed = _Entry(id=1, register='vehicle_inspection', ref='VIN-0001',
                   entry_date=TODAY, schedule_id=5, occurrence_date=TODAY,
                   asset_id=11, created_by=_User('M. Dube'))
    grouped = items_by_day([vehicles()], [filed], TODAY, TODAY, TODAY)
    cards = drawer_cards(grouped[TODAY], TODAY)
    assert len(cards) == 2
    assert any(c['state'] == 'done' for c in cards)


def test_a_card_carries_what_log_it_needs():
    grouped = items_by_day([vehicles()], [], TODAY, TODAY, TODAY)
    card = drawer_cards(grouped[TODAY], TODAY)[0]
    assert card['register'] == 'vehicle_inspection'
    assert card['schedule_id'] == 5
    assert card['asset_id'] in (11, 12)
    assert card['date'] == TODAY


def test_a_logged_card_does_not_print_its_register_twice():
    """A logged card has no subtitle, since its title is already the register name."""
    incident = _Entry(id=9, register='incidents', ref='INC-0009',
                      entry_date=TODAY)
    grouped = items_by_day([], [incident], TODAY, TODAY, TODAY)
    card = drawer_cards(grouped[TODAY], TODAY)[0]
    assert card['title'] == 'Incident & near miss'
    assert card['subtitle'] is None


def test_an_expiring_card_keeps_its_register_line():
    """An expiring card keeps the register name as its subtitle."""
    cert = _Entry(id=3, register='compliance_renewal', ref='COM-0004',
                  entry_date=date(2026, 6, 1), due_at=date(2026, 9, 30),
                  compliance_item=_Ref(3, 'ISO 45001 Certification'))
    grouped = items_by_day([], [cert], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    card = drawer_cards(grouped[date(2026, 9, 30)], TODAY)[0]
    assert card['subtitle'] == 'Compliance & renewal'


def test_an_expiring_card_counts_down():
    cert = _Entry(id=3, register='compliance_renewal', ref='COM-0004',
                  entry_date=date(2026, 6, 1), due_at=date(2026, 9, 30),
                  compliance_item=_Ref(3, 'ISO 45001 Certification'))
    grouped = items_by_day([], [cert], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    card = drawer_cards(grouped[date(2026, 9, 30)], TODAY)[0]
    assert card['title'] == 'ISO 45001 Certification'
    assert card['meta'] == 'Expires 30 Sep · 16 days left'


def test_the_day_summary_never_double_counts():
    """The day summary counts a done card as done only, not also due."""
    filed = _Entry(id=1, register='vehicle_inspection', ref='VIN-0001',
                   entry_date=TODAY, schedule_id=5, occurrence_date=TODAY,
                   asset_id=11)
    grouped = items_by_day([vehicles()], [filed], TODAY, TODAY, TODAY)
    assert day_summary(drawer_cards(grouped[TODAY], TODAY)) == '1 due · 1 done'


def test_the_day_summary_calls_out_overdue():
    grouped = items_by_day([vehicles()], [], date(2026, 9, 7), date(2026, 9, 7), TODAY)
    assert day_summary(drawer_cards(grouped[date(2026, 9, 7)], TODAY)) \
        == '2 due · 2 overdue'


def test_the_agenda_renders_the_same_cards_as_the_drawer():
    """Agenda groups use the same cards and summary as the drawer."""
    grouped = items_by_day([vehicles()], [], TODAY, date(2026, 10, 14), TODAY)
    group = agenda_groups(grouped, TODAY)[0]
    assert group['cards'] == drawer_cards(grouped[group['date']], TODAY)
    assert group['summary'] == day_summary(group['cards'])


# --- the Jinja shadowing trap ---------------------------------------------

def test_no_view_model_uses_a_key_jinja_would_read_as_a_dict_method():
    """No template dict uses a key like `items` that Jinja resolves to a dict method.

    Jinja tries attributes before subscripts, so {{ d.items }} gives the bound method.
    """
    day = date(2026, 9, 7)
    incident = _Entry(id=1, register='incidents', ref='INC-0001', entry_date=day)
    grouped = items_by_day([vehicles()], [incident], day, day, TODAY)
    ahead = items_by_day([vehicles()], [], TODAY, date(2026, 10, 14), TODAY)

    cells = [d for week in month_grid(grouped, 2026, 9, TODAY) for d in week]
    groups = agenda_groups(ahead, TODAY)
    items = [i for day_items in grouped.values() for i in day_items]
    targets = [t for i in items for t in i['targets']]
    cards = drawer_cards(grouped.get(day, []), TODAY)
    drawer = {'date': day, 'cards': cards, 'summary': day_summary(cards)}

    checked = (cells + groups + items + targets + cards
               + state_chips(grouped, None)
               + [kpis([vehicles()], [], date(2026, 9, 1), date(2026, 9, 30), TODAY)]
               + [drawer])
    assert items and targets and groups and cards, 'the fixture stopped covering anything'

    for mapping in checked:
        bad = shadowed_keys(mapping)
        assert not bad, (
            'These keys would resolve to a dict method in a template: '
            + ', '.join(bad) + f' (in {sorted(mapping)})')


# --- url helpers ----------------------------------------------------------

def test_month_parsing_falls_back_to_this_month():
    assert parse_month('2026-11', TODAY) == (2026, 11)
    assert parse_month('2026-13', TODAY) == (2026, 9)
    assert parse_month('rubbish', TODAY) == (2026, 9)
    assert parse_month(None, TODAY) == (2026, 9)


def test_shifting_months_crosses_the_year():
    assert shift_month(2026, 12, 1) == (2027, 1)
    assert shift_month(2026, 1, -1) == (2025, 12)


def test_day_parsing_rejects_nonsense():
    assert parse_day('2026-09-14') == date(2026, 9, 14)
    assert parse_day('not a day') is None
    assert parse_day(None) is None


def test_daily_checks_fold_into_one_line_after_the_one_off_items():
    """Daily schedules fold into one "Daily checks" chip, after one-off items; the drawer keeps all."""
    day = date(2026, 9, 10)
    daily = [_Schedule(id=20 + n, register='forklift_inspection', label=f'Daily {n}',
                       frequency='daily', interval=1, active=True,
                       starts_on=date(2026, 9, 1)) for n in range(2)]
    incident = _Entry(id=1, register='incidents', ref='INC-0001', entry_date=day)
    grouped = items_by_day(daily, [incident], day, day, TODAY)
    cell = next(d for week in month_grid(grouped, 2026, 9, TODAY) for d in week
                if d['date'] == day)
    labels = [i['label'] for i in cell['shown']]
    assert labels[-1] == 'Daily checks · 2'
    assert len(labels) == 2 and cell['more'] == 0
    assert len(cell['day_items']) == 3   # the drawer still has all of them
