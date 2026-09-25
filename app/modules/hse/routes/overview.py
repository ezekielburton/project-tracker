"""
HSE — the Overview. The module's front page.

It answers one question in its first screen: what needs him today. The
tiles are counts of things elsewhere, and every panel row links to the
entry behind it, so nothing here is a dead end.

No metric is defined in this file. Compliance health, coverage and the SLA
clock all come from lib/metrics.py, which My performance reads too.
"""
from datetime import date, timedelta

from flask import render_template
from flask_login import login_required
from sqlalchemy.orm import selectinload

from app.modules.core.shared.lib.capabilities import require
from app.modules.hse.lib.calendar import shift_month
from app.modules.hse.lib.overview import (
    expiring_panel, needs_you_now, severity_breakdown, this_week, tiles,
    waiting_on_others,
)
from app.modules.hse.lib.query import dashboard_entries, open_counts_by_group
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.models import HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


@hse_bp.route('/overview')
@login_required
@require('view_hse')
def overview():
    today = date.today()
    entries = dashboard_entries(today)
    schedules = (HseSchedule.query
                 .options(selectinload(HseSchedule.assets))
                 .all())

    month_start = date(today.year, today.month, 1)
    month_end = date(*shift_month(today.year, today.month, 1), 1) - timedelta(days=1)
    counts, health = tiles(schedules, entries, month_start, month_end, today)

    # The week he is in, Monday to Sunday — the same week the calendar
    # draws and the weekly HSC report covers.
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Severity reads over the year: a month is too few incidents for the
    # shape of the bars to mean anything.
    year_start = date(today.year, 1, 1)

    return render_template(
        'hse/overview.html',
        tiles=counts,
        health=health,
        needs=needs_you_now(entries, today),
        waiting=waiting_on_others(entries, today),
        expiring=expiring_panel(health, today),
        week=this_week(schedules, entries, week_start, week_end, today),
        week_label=week_start.strftime('%d %b'),
        severity=severity_breakdown(entries, year_start, today),
        year_label=today.year,
        month_label=month_start.strftime('%B'),
        today=today,
        rail=rail_items(open_counts_by_group(today), active_group='overview'),
        active_group='overview',
    )
