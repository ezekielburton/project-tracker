"""
HSE — My performance.

Gated view_hse, so management and admin read it too: this page is written to
be taken into a review, and a page only its subject can see is no use there.

Nothing is defined here. Every number comes from lib/performance.py, which
reads lib/metrics.py, which the Overview and the calendar read as well.
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
    expiring_next, open_by_age, period, read_outs, reporting,
    schedule_coverage, sla_table, tiles, trend_months,
)
from app.modules.hse.lib.query import dashboard_entries, open_counts_by_group
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.models import HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


# The charts run over the trailing twelve months and the tiles compare
# against the twelve before that, so two years plus a margin is the window.
LOOKBACK_DAYS = 800


def _anchor():
    """The month the page is showing. A bad or missing date lands on today
    rather than erroring — a mistyped URL should not be a 500."""
    raw = request.args.get('month')
    if raw:
        try:
            return date.fromisoformat(raw + '-01')
        except ValueError:
            pass
    return date.today()


def _view_model(today=None):
    today = today or date.today()
    window = period(request.args.get('view'), _anchor())

    entries = dashboard_entries(today, LOOKBACK_DAYS)
    schedules = (HseSchedule.query
                 .options(selectinload(HseSchedule.assets))
                 .all())

    months = trend_months(window['end'])
    cover = coverage_series(schedules, entries, months, today)
    ageing = age_series(entries, months)
    return {
        'window': window,
        'tiles': tiles(schedules, entries, window, today),
        'bars': charts.grouped_bars(cover),
        'line': charts.line(ageing),
        'reporting': reporting(entries, window),
        'compliance': compliance_panel(entries, window, today),
        'ageing': open_by_age(entries, today),
        'today': today,
        # The report needs these again for its own sections and to redraw
        # the charts at print width. The page drops them; nothing renders
        # from them directly.
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
        rail=rail_items(open_counts_by_group(model['today']), active_group='performance'),
        active_group='performance',
        **model)


@hse_bp.route('/performance/report')
@login_required
@require('view_hse')
def performance_report():
    """The four-page A4 report, printed from the browser.

    Same view model as the page — the report cannot quote a different number
    from the screen it was exported off. `auto` opens the print dialog on
    load, which is what "Export for review" does.
    """
    model = _view_model()
    entries = model.pop('_entries')
    schedules = model.pop('_schedules')
    window = model['window']

    # Redrawn narrower: an A4 column is about half the width of the page's,
    # and a chart sized for the screen would print its labels at half size.
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
