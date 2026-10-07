from datetime import date, datetime

from app.modules.reports.lib.period import Period, WEEKLY, MONTHLY


def test_week_is_monday_to_friday():
    p = Period.week_of(date(2026, 10, 1))  # Thursday
    assert (p.start, p.end) == (date(2026, 9, 28), date(2026, 10, 2))


def test_last_complete_week_on_a_monday():
    p = Period.last_complete(WEEKLY, date(2026, 10, 5))
    assert (p.start, p.end) == (date(2026, 9, 28), date(2026, 10, 2))


def test_last_complete_month_on_the_first():
    p = Period.last_complete(MONTHLY, date(2026, 10, 1))
    assert (p.start, p.end) == (date(2026, 9, 1), date(2026, 9, 30))


def test_previous_crosses_year_end():
    assert Period.week_of(date(2027, 1, 5)).previous().start == date(2026, 12, 28)
    assert Period.month_of(date(2027, 1, 5)).previous().start == date(2026, 12, 1)


def test_utc_bounds_use_dubai_midnight():
    start, end = Period.week_of(date(2026, 9, 28)).utc_bounds()
    assert start == datetime(2026, 9, 27, 20, 0)  # Mon 00:00 Dubai
    assert end == datetime(2026, 10, 2, 20, 0)    # Sat 00:00 Dubai


def test_working_days_in_september_2026():
    assert len(Period.month_of(date(2026, 9, 1)).working_days()) == 22


def test_labels():
    w = Period.week_of(date(2026, 9, 29))
    assert w.label == 'Week 40 · Mon 28 Sep – Fri 2 Oct 2026'
    assert w.short_label == 'Wk 40 · 28 Sep – 2 Oct'
    assert w.file_stem == 'Wk40'
    m = Period.month_of(date(2026, 9, 1))
    assert m.label == 'September 2026 · 22 working days'
    assert m.file_stem == '2026-09'


def test_scheduled_send_is_next_monday_0800_dubai():
    w = Period.week_of(date(2026, 9, 28))
    assert w.scheduled_send_at() == datetime(2026, 10, 5, 4, 0)  # 08:00 Dubai
