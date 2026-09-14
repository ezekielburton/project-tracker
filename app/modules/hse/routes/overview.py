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
    expiring_panel, needs_you_now, tiles, waiting_on_others,
)
from app.modules.hse.lib.query import open_counts_by_group
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.models import HseEntry, HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


# Entries older than this cannot be open, expiring, or this month's work.
# A cap keeps the front page from slowing down as the registers fill.
LOOKBACK_DAYS = 400


def _entries(today):
    return (HseEntry.query
            .options(selectinload(HseEntry.asset),
                     selectinload(HseEntry.reported_by),
                     selectinload(HseEntry.assigned_to),
                     selectinload(HseEntry.subject),
                     selectinload(HseEntry.waiting_on))
            .filter(HseEntry.entry_date >= today - timedelta(days=LOOKBACK_DAYS))
            .all())


@hse_bp.route('/overview')
@login_required
@require('view_hse')
def overview():
    today = date.today()
    entries = _entries(today)
    schedules = (HseSchedule.query
                 .options(selectinload(HseSchedule.assets))
                 .all())

    month_start = date(today.year, today.month, 1)
    month_end = date(*shift_month(today.year, today.month, 1), 1) - timedelta(days=1)
    counts, health = tiles(schedules, entries, month_start, month_end, today)

    return render_template(
        'hse/overview.html',
        tiles=counts,
        health=health,
        needs=needs_you_now(entries, today),
        waiting=waiting_on_others(entries, today),
        expiring=expiring_panel(health, today),
        month_label=month_start.strftime('%B'),
        today=today,
        rail=rail_items(open_counts_by_group(today), active_group='overview'),
        active_group='overview',
    )
