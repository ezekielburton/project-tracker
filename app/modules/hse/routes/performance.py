"""
HSE My performance, plus its printable review report.

Gated view_hse so management can read it in a review. No metric is defined
here: numbers come from lib/performance.py, built on lib/metrics.py (shared
with the Overview).
"""
from datetime import date

from flask import Response, jsonify, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.orm import selectinload

from app.modules.core.shared.lib.capabilities import effective_user, require, require_api
from app.modules.core.shared.lib.utils import log_activity
from app.modules.hse.lib import charts, share
from app.modules.hse.lib.flags import rail_counts
from app.modules.hse.lib.metrics import training_delivered
from app.modules.hse.lib.performance import (
    age_series, closed_by_severity, compliance_panel, coverage_series,
    expiring_next, navigation, open_by_age, period, read_outs, reporting,
    schedule_coverage, sla_table, tiles, trend_months,
)
from app.modules.hse.lib.query import dashboard_entries
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
    window = model['window']
    return render_template(
        'hse/performance.html',
        rail=rail_items(rail_counts(model['today']), active_group='performance'),
        active_group='performance',
        share_people=share.people(effective_user()),
        share_url=url_for('hse.performance_share', view=window['view'],
                          month=window['end'].strftime('%Y-%m')),
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


@hse_bp.route('/performance/export.csv')
@login_required
@require('view_hse')
def performance_csv():
    """The page's figures for the period shown, as a spreadsheet."""
    model = _view_model()
    window = model['window']
    name = f"hse-performance-{window['view']}-{window['end'].strftime('%Y-%m')}.csv"
    return Response(share.performance_csv(model), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={name}'})


@hse_bp.route('/performance/share', methods=['POST'])
@login_required
@require_api('view_hse')
def performance_share():
    """Email the tiles for the period in the query string, with a link to
    the printable report."""
    model = _view_model()
    window = model['window']
    sender = effective_user()
    payload = request.get_json(silent=True) or {}
    link = share.absolute_url(url_for('hse.performance_report', view=window['view'],
                                      month=window['end'].strftime('%Y-%m')))
    try:
        sent = share.send(sender, payload.get('to'), payload.get('note'),
                          'HSE performance', window['label'],
                          share.figures(model['tiles']), link)
    except share.ShareError as e:
        return jsonify({'error': e.message}), e.status
    log_activity('hse_report_emailed',
                 f"{sender.name} emailed HSE performance ({window['label']}) to {len(sent)}",
                 user=sender, entity_type='hse_report', entity_name=window['label'])
    return jsonify({'sent': [u.name for u in sent]})
