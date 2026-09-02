"""Coverage for the Digital Innovation period math + rollover overlap
query (lib/periods.py, brain B). Pure date arithmetic plus one query
against the database, same split test_costs_lib.py uses for brain A's
HTTP-free half."""
import datetime

import pytest

from app.modules.digital_innovation.models import DiProject
from app.modules.digital_innovation.lib import periods


def _project(db_session, tag, created_at=None, closed_at=None, lifecycle='active'):
    project = DiProject(
        name=f'Test DI Project {tag}',
        lifecycle=lifecycle,
        created_at=created_at or datetime.datetime(2026, 1, 1),
        closed_at=closed_at,
    )
    db_session.add(project)
    db_session.flush()
    return project


# ── current_period_key / period_bounds ──────────────────────────────────

def test_current_period_key_week():
    assert periods.current_period_key('week', today=datetime.date(2026, 8, 19)) == '2026-W34'


def test_current_period_key_month():
    assert periods.current_period_key('month', today=datetime.date(2026, 8, 19)) == '2026-08'


def test_current_period_key_quarter():
    assert periods.current_period_key('quarter', today=datetime.date(2026, 8, 19)) == '2026-Q3'


def test_period_bounds_week_is_monday_to_sunday():
    start, end = periods.period_bounds('week', '2026-W34')
    assert start == datetime.date(2026, 8, 17)
    assert end == datetime.date(2026, 8, 23)


def test_period_bounds_month():
    start, end = periods.period_bounds('month', '2026-09')
    assert start == datetime.date(2026, 9, 1)
    assert end == datetime.date(2026, 9, 30)


def test_period_bounds_quarter():
    start, end = periods.period_bounds('quarter', '2026-Q4')
    assert start == datetime.date(2026, 10, 1)
    assert end == datetime.date(2026, 12, 31)


def test_period_bounds_rejects_an_unknown_type():
    with pytest.raises(ValueError):
        periods.period_bounds('fortnight', '2026-01')


# ── shift_period ─────────────────────────────────────────────────────────

def test_shift_period_week_forward():
    assert periods.shift_period('week', '2026-W34', 1) == '2026-W35'


def test_shift_period_week_backward():
    assert periods.shift_period('week', '2026-W34', -1) == '2026-W33'


def test_shift_period_month_rolls_into_next_year():
    assert periods.shift_period('month', '2026-12', 1) == '2027-01'


def test_shift_period_quarter_rolls_into_next_year():
    assert periods.shift_period('quarter', '2026-Q4', 1) == '2027-Q1'


def test_shift_period_quarter_backward_rolls_into_previous_year():
    assert periods.shift_period('quarter', '2027-Q1', -1) == '2026-Q4'


# ── format_period_label ────────────────────────────────────────────────

def test_format_period_label_week_within_one_month():
    assert periods.format_period_label('week', '2026-W34') == 'Week 34, Aug 17-23, 2026'


def test_format_period_label_month():
    assert periods.format_period_label('month', '2026-09') == 'September 2026'


def test_format_period_label_quarter():
    assert periods.format_period_label('quarter', '2026-Q3') == 'Q3 2026'


# ── period_has_ended ───────────────────────────────────────────────────

def test_period_has_ended_true_for_a_past_month():
    assert periods.period_has_ended('month', '2026-01', today=datetime.date(2026, 9, 1)) is True


def test_period_has_ended_false_for_the_current_month():
    assert periods.period_has_ended('month', '2026-09', today=datetime.date(2026, 9, 15)) is False


def test_period_has_ended_false_for_a_future_month():
    assert periods.period_has_ended('month', '2026-12', today=datetime.date(2026, 9, 1)) is False


# ── projects_overlapping ─────────────────────────────────────────────────

def test_projects_overlapping_includes_a_still_active_project_created_before_the_period(db_session):
    project = _project(db_session, 'a', created_at=datetime.datetime(2026, 1, 1))
    start, end = periods.period_bounds('week', '2026-W34')
    assert project in periods.projects_overlapping(start, end)


def test_projects_overlapping_excludes_a_project_created_after_the_period(db_session):
    project = _project(db_session, 'b', created_at=datetime.datetime(2026, 9, 1))
    start, end = periods.period_bounds('week', '2026-W34')
    assert project not in periods.projects_overlapping(start, end)


def test_projects_overlapping_includes_the_week_a_project_closed_in(db_session):
    project = _project(
        db_session, 'c',
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 8, 19),  # Wednesday of week 34
        lifecycle='closed',
    )
    start, end = periods.period_bounds('week', '2026-W34')
    assert project in periods.projects_overlapping(start, end)


def test_projects_overlapping_drops_off_the_week_after_it_closed(db_session):
    project = _project(
        db_session, 'd',
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 8, 19),  # week 34
        lifecycle='closed',
    )
    start, end = periods.period_bounds('week', '2026-W35')
    assert project not in periods.projects_overlapping(start, end)


def test_projects_overlapping_stays_in_the_month_it_closed_in(db_session):
    project = _project(
        db_session, 'e',
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 8, 19),  # closed mid-August
        lifecycle='closed',
    )
    start, end = periods.period_bounds('month', '2026-08')
    assert project in periods.projects_overlapping(start, end)


def test_projects_overlapping_excludes_a_project_closed_before_the_period_started(db_session):
    project = _project(
        db_session, 'f',
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 1, 15),
        lifecycle='closed',
    )
    start, end = periods.period_bounds('month', '2026-09')
    assert project not in periods.projects_overlapping(start, end)
