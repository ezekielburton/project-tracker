"""
HSE Overview: the module's front page, showing what needs attention today.

No metric is defined here; compliance health, coverage and the SLA clock
come from lib/metrics.py, shared with My performance.
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
from app.modules.hse.lib.query import (
    dashboard_entries, open_counts_by_register, spend_entries,
)
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.lib.spend import spend_panel
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

    # Monday to Sunday, matching the calendar week and the weekly HSC report.
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Severity covers the year: a month has too few incidents to be meaningful.
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
        # All time, so not dashboard_entries: the register strips share this loader.
        spend=spend_panel(spend_entries(), today),
        year_label=today.year,
        month_label=month_start.strftime('%B'),
        today=today,
        rail=rail_items(open_counts_by_register(today), active_group='overview'),
        active_group='overview',
    )
