"""
HSE Statistics: what happened on site over a period (lib/statistics.py).
The period is in the URL (?period=month|quarter|year&year=YYYY). The weekly
and monthly reports print the same figures (lib/reports.py).
"""
from datetime import date

from flask import abort, jsonify, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.orm import selectinload

from app.modules.core.shared.lib.capabilities import effective_user, require, require_api
from app.modules.core.shared.lib.utils import log_activity
from app.modules.hse.lib import charts, reports, share
from app.modules.hse.lib import statistics as stats
from app.modules.hse.lib.flags import load_flags, rail_counts
from app.modules.hse.lib.overview import this_week
from app.modules.hse.lib.query import (
    dashboard_entries, first_entry_year, statistics_entries,
)
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.models import HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


@hse_bp.route('/statistics')
@login_required
@require('view_hse')
def statistics():
    today = date.today()
    raw_year = request.args.get('year') or ''
    window = stats.period(request.args.get('period'),
                          int(raw_year) if raw_year.isdigit() else None, today)
    entries = statistics_entries(stats.load_from(window))
    model = stats.view_model(entries, window, today)

    def link(**args):
        return url_for('hse.statistics', **{k: v for k, v in args.items() if v})

    return render_template(
        'hse/statistics.html',
        **model,
        bars=charts.grouped_bars(model['series'], keys=('incidents', 'near'),
                                 aria='Incidents and near misses, by month'),
        periods=[{'label': label, 'url': link(period=key),
                  'on': window['view'] == key}
                 for key, (label, _) in stats.PERIODS.items() if key != 'year'],
        years=[{'value': y, 'url': link(period='year', year=y),
                'on': window['view'] == 'year' and window['year'] == y}
               for y in stats.year_choices(today, first_entry_year())],
        rail=rail_items(rail_counts(today), active_group='statistics'),
        active_group='statistics',
    )


@hse_bp.route('/statistics/report/<kind>')
@login_required
@require('view_hse')
def statistics_report(kind):
    """The weekly or monthly report for the period holding ?at=YYYY-MM-DD
    (default today). Printed from the browser, like My performance's report."""
    today = date.today()
    window = _report_window(kind, today)

    entries = statistics_entries(stats.load_from(window))
    schedules = HseSchedule.query.options(selectinload(HseSchedule.assets)).all()
    model = stats.view_model(entries, window, today)

    return render_template(
        'hse/statistics_report.html',
        **model,
        kind=kind,
        nav=reports.navigation(window, today),
        glance=this_week(schedules, entries, window['start'], window['end'], today),
        incidents=reports.incident_rows(entries, window, reports.INCIDENT_ROWS),
        attention=reports.attention(dashboard_entries(today), load_flags(today), today),
        bars=charts.grouped_bars(model['series'], width=charts.PRINT_WIDTH, height=220,
                                 keys=('incidents', 'near'),
                                 aria='Incidents and near misses, by month'),
        today=today,
        share_people=share.people(effective_user()),
        share_url=url_for('hse.statistics_report_share', kind=kind,
                          at=window['start'].isoformat()),
    )


def _report_window(kind, today):
    """The report period for ?at=YYYY-MM-DD (default today); 404 for an
    unknown kind."""
    if kind not in reports.KINDS:
        abort(404)
    try:
        at = date.fromisoformat(request.args.get('at') or '')
    except ValueError:
        at = None
    return reports.window(kind, at, today)


@hse_bp.route('/statistics/report/<kind>/share', methods=['POST'])
@login_required
@require_api('view_hse')
def statistics_report_share(kind):
    """Email a weekly or monthly report's tiles with a link to the report."""
    today = date.today()
    window = _report_window(kind, today)
    entries = statistics_entries(stats.load_from(window))
    sender = effective_user()
    payload = request.get_json(silent=True) or {}
    title = 'Weekly HSE report' if kind == 'week' else 'Monthly HSE report'
    link = share.absolute_url(url_for('hse.statistics_report', kind=kind,
                                      at=window['start'].isoformat()))
    try:
        sent = share.send(sender, payload.get('to'), payload.get('note'), title,
                          window['label'], share.figures(stats.tiles(entries, window, today)),
                          link)
    except share.ShareError as e:
        return jsonify({'error': e.message}), e.status
    log_activity('hse_report_emailed',
                 f"{sender.name} emailed the {title.lower()} ({window['label']}) to {len(sent)}",
                 user=sender, entity_type='hse_report', entity_name=window['label'])
    return jsonify({'sent': [u.name for u in sent]})
