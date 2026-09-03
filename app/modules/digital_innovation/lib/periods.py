# Period math + the rollover overlap query. Pure date arithmetic and the "which
# projects belong in this window" query live here; lib/snapshots.py turns a
# window into the actual rollup numbers (and freezes month/quarter ones once
# they've ended).
#
# A project "belongs" to a period if its active lifespan overlaps that
# period's date range at all — lifespan = [created_at, closed_at] once
# closed/archived, or [created_at, "still open"] while active. This one
# rule is what makes a project closed mid-week drop off the FOLLOWING
# week's table on its own (closed_at ends its lifespan there) while it
# still shows up in whatever month/quarter contains the week it closed
# in — no special-casing per granularity, just the same overlap check at
# three widths.

import calendar
from datetime import date, datetime, timedelta

from sqlalchemy import or_

from app.modules.digital_innovation.models import DiProject

PERIOD_TYPES = ('week', 'month', 'quarter')
PERIOD_VIEW_LABELS = {'week': 'Weekly', 'month': 'Monthly', 'quarter': 'Quarterly'}


def _iso_week_bounds(year, week):
    monday = date.fromisocalendar(year, week, 1)
    return monday, monday + timedelta(days=6)


def _month_bounds(year, month):
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    return first, date(year, month, last_day)


def _quarter_bounds(year, quarter):
    first_month = (quarter - 1) * 3 + 1
    last_month = first_month + 2
    last_day = calendar.monthrange(year, last_month)[1]
    return date(year, first_month, 1), date(year, last_month, last_day)


def current_period_key(period_type, today=None):
    """The period_key covering `today` (defaults to date.today())."""
    today = today or date.today()
    if period_type == 'week':
        iso_year, iso_week, _ = today.isocalendar()
        return f'{iso_year}-W{iso_week:02d}'
    if period_type == 'month':
        return f'{today.year}-{today.month:02d}'
    if period_type == 'quarter':
        return f'{today.year}-Q{(today.month - 1) // 3 + 1}'
    raise ValueError(f"Unknown period type '{period_type}'.")


def period_bounds(period_type, period_key):
    """(start_date, end_date), inclusive, for a period_key like
    '2026-W34', '2026-09', or '2026-Q3'."""
    if period_type == 'week':
        year_str, week_str = period_key.split('-W')
        return _iso_week_bounds(int(year_str), int(week_str))
    if period_type == 'month':
        year_str, month_str = period_key.split('-')
        return _month_bounds(int(year_str), int(month_str))
    if period_type == 'quarter':
        year_str, q_str = period_key.split('-Q')
        return _quarter_bounds(int(year_str), int(q_str))
    raise ValueError(f"Unknown period type '{period_type}'.")


def shift_period(period_type, period_key, direction):
    """The period_key one step before (direction<0) or after
    (direction>0) the given one. Steps a day past the current period's
    start/end and re-derives the key from that date — the simplest way
    to get correct month/quarter rollover (e.g. Q4 2026 -> Q1 2027)
    without hand-rolling calendar math twice."""
    start, end = period_bounds(period_type, period_key)
    anchor = (start - timedelta(days=1)) if direction < 0 else (end + timedelta(days=1))
    return current_period_key(period_type, today=anchor)


def format_period_label_parts(period_type, period_key):
    """(primary, secondary) for the Performance header's two-line period
    display — e.g. ('Week 34', 'Aug 17-23, 2026') for a week. A month or
    quarter's whole label already reads fine as one line, so secondary is
    '' for those (the template just skips rendering a second line when
    it's empty). format_period_label() below is the single-string form
    older/other callers use — it's built from this pair rather than
    duplicating the same date arithmetic twice."""
    start, end = period_bounds(period_type, period_key)
    if period_type == 'week':
        _, week_num, _ = start.isocalendar()
        if start.month == end.month:
            range_str = f'{start.strftime("%b")} {start.day}-{end.day}, {end.year}'
        else:
            range_str = f'{start.strftime("%b %d")} - {end.strftime("%b %d")}, {end.year}'
        return f'Week {week_num}', range_str
    if period_type == 'month':
        return start.strftime('%B %Y'), ''
    if period_type == 'quarter':
        return f'Q{(start.month - 1) // 3 + 1} {start.year}', ''
    raise ValueError(f"Unknown period type '{period_type}'.")


def format_period_label(period_type, period_key):
    """Human label for the period header, e.g. 'Week 34, Aug 17-23,
    2026', 'September 2026', 'Q3 2026'."""
    primary, secondary = format_period_label_parts(period_type, period_key)
    return f'{primary}, {secondary}' if secondary else primary


def period_has_ended(period_type, period_key, today=None):
    """True once the period's last day is in the past — the trigger
    lib/snapshots.py uses to decide whether a month/quarter is eligible
    to be frozen. Weekly periods never freeze, but this still answers
    honestly for them; callers just never act on it for 'week'."""
    today = today or date.today()
    _, end = period_bounds(period_type, period_key)
    return end < today


def projects_overlapping(period_start, period_end):
    """Every DiProject whose active lifespan touches [period_start,
    period_end] at all — the rollover query itself. A still-active project has
    no end to its lifespan, so it overlaps any period
    from its creation date onward; a closed/archived one's lifespan ends
    at closed_at, so it stops overlapping periods entirely after the one
    it closed in."""
    period_start_dt = datetime.combine(period_start, datetime.min.time())
    period_end_dt = datetime.combine(period_end, datetime.max.time())
    return (
        DiProject.query
        .filter(
            DiProject.created_at <= period_end_dt,
            or_(DiProject.closed_at.is_(None), DiProject.closed_at >= period_start_dt),
        )
        .order_by(DiProject.is_permanent.desc(), DiProject.created_at.asc())
        .all()
    )
