"""The shared month grid: Monday-first weeks covering the whole month."""
from datetime import date

from app.modules.core.shared.lib.month_grid import month_span, month_weeks


def test_month_weeks_run_monday_first_and_cover_the_month():
    weeks = month_weeks(2026, 2, date(2026, 2, 14))
    assert all(len(week) == 7 for week in weeks)
    assert weeks[0][0]['date'].weekday() == 0
    in_month = [day['date'] for week in weeks for day in week if day['in_month']]
    assert (in_month[0], in_month[-1]) == (date(2026, 2, 1), date(2026, 2, 28))
    assert [day['date'] for week in weeks for day in week if day['is_today']] == [date(2026, 2, 14)]


def test_month_span_is_the_first_and_last_day_drawn():
    assert month_span(2026, 2) == (date(2026, 1, 26), date(2026, 3, 1))


def test_events_land_on_their_day():
    day = date(2026, 2, 10)
    weeks = month_weeks(2026, 2, day, {day: ['a', 'b']})
    cell = next(d for week in weeks for d in week if d['date'] == day)
    assert (cell['events'], cell['count']) == (['a', 'b'], 2)
