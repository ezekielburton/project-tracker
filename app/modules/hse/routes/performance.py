"""
HSE My performance, plus its printable review report.

Gated view_hse so management can read it in a review. No metric is defined
here: numbers come from lib/performance.py, built on lib/metrics.py (shared
with the Overview).
"""
from datetime import date

from flask import render_template, request
from flask_login import login_required
from sqlalchemy.orm import selectinload

from app.modules.core.shared.lib.capabilities import require
from app.modules.hse.lib import charts
from app.modules.hse.lib.metrics import training_delivered
from app.modules.hse.lib.performance import (
    age_series, closed_by_severity, compliance_panel, coverage_series,
    expiring_next, navigation, open_by_age, period, read_outs, reporting,
    schedule_coverage, sla_table, tiles, trend_months,
)
from app.modules.hse.lib.query import dashboard_entries, open_counts_by_register
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.models import HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


# Charts cover 12 trailing months and tiles compare with the 12 before,
# so load two years plus a margin.
LOOKBACK_DAYS = 800


def _anchor(today):
    """The month shown, from ?month=YYYY-MM. Missing or invalid means today;
    a future month is clamped to today."""
    raw = request.args.get('month')
    if raw:
        try:
            return min(date.fromisoformat(raw + '-01'), today)
        except ValueError:
            pass
    return today


def _view_model(today=None):
    today = today or date.today()
    window = period(request.args.get('view'), _anchor(today))

    entries = dashboard_entries(today, LOOKBACK_DAYS)
    schedules = (HseSchedule.query
                 .options(selectinload(HseSchedule.assets))
                 .all())

    months = trend_months(window['end'])
    cover = coverage_series(schedules, entries, months, today)
    ageing = age_series(entries, months)
    return {
        'window': window,
        'nav': navigation(window, today),
        'tiles': tiles(schedules, entries, window, today),
        'bars': charts.grouped_bars(cover),
        'line': charts.line(ageing),
        'reporting': reporting(entries, window),
        'compliance': compliance_panel(entries, window, today),
        'ageing': open_by_age(entries, today),
        'today': today,
        # Report-only inputs (extra sections, print-width charts); the page
        # pops them before rendering.
        '_entries': entries,
        '_schedules': schedules,
        '_cover': cover,
        '_ageing': ageing,
    }


@hse_bp.route('/performance')
@login_required
@require('view_hse')
def performance():
    model = _view_model()
    for key in ('_entries', '_schedules', '_cover', '_ageing'):
        model.pop(key)
    return render_template(
        'hse/performance.html',
        rail=rail_items(open_counts_by_register(model['today']), active_group='performance'),
        active_group='performance',
        **model)


@hse_bp.route('/performance/report')
@login_required
@require('view_hse')
def performance_report():
    """Four-page A4 report, printed from the browser. Shares the page's view
    model so the numbers always match. `auto=1` ("Export for review") opens
    the print dialog on load.
    """
    model = _view_model()
    entries = model.pop('_entries')
    schedules = model.pop('_schedules')
    window = model['window']

    # Redraw at print width so labels print at a readable size on A4.
    model['bars'] = charts.grouped_bars(model.pop('_cover'),
                                        width=charts.PRINT_WIDTH, height=230)
    model['line'] = charts.line(model.pop('_ageing'),
                                width=charts.PRINT_WIDTH, height=210)

    return render_template(
        'hse/performance_report.html',
        sla=sla_table(),
        severity_rows=closed_by_severity(entries, window, model['today']),
        schedule_rows=schedule_coverage(schedules, entries, window, model['today']),
        training=training_delivered(entries, window['start'], window['end']),
        expiring=expiring_next(entries, model['today']),
        callouts=read_outs(model['tiles'], model['reporting'],
                           model['compliance'], model['ageing']),
        auto=request.args.get('auto') == '1',
        **model)
