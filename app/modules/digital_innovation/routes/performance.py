# Digital Innovation — Performance view (restricted, see lib/access.py).
# Weekly/monthly/quarterly rollups + summary cards. Thin HTTP layer only:
# everything about what a period "is" and what it adds up to lives in
# lib/periods.py (brain B, the rollover overlap query) and
# lib/snapshots.py (brain C, the month/quarter freeze) — this file just
# resolves the view/period query params, calls get_period_rollup(), and
# renders. No fragment/AJAX route: the Weekly/Monthly/Quarterly tabs and
# the prev/next arrows are plain links, handled by the app's existing
# SPA-nav plumbing like any other Digital Innovation page (board.py's
# board_columns_fragment exists because the board needed a live SSE-
# driven refresh; Performance has no live-update requirement, so it
# doesn't need that extra route). The Excel export below is the one other
# route this page needs — same shape as costs.py's export_cost_ledger,
# streaming whatever the current view/period's rollup already is rather
# than re-querying (Ezekiel's wireframe, 2 Sep 2026).

from flask import render_template, request, abort, send_file
from flask_login import login_required, current_user

from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.lib.access import can_view_di_performance, can_edit_di_templates, can_edit_di_board
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project
from app.modules.digital_innovation.lib import periods, snapshots, costs
from app.modules.digital_innovation.lib.excel_export import build_performance_workbook


def _resolve_view_and_period():
    """Reads view/period off the querystring, defaulting to the current
    week. A bad/unknown view or period_key falls back to today's period
    for that view rather than 400ing — this is just navigation state,
    not a form submission, so a stale or hand-edited URL should degrade
    gracefully instead of erroring."""
    view = request.args.get('view', 'week')
    if view not in periods.PERIOD_TYPES:
        view = 'week'

    period_key = request.args.get('period') or periods.current_period_key(view)
    try:
        periods.period_bounds(view, period_key)
    except (ValueError, TypeError):
        period_key = periods.current_period_key(view)

    return view, period_key


@digital_innovation_bp.route('/performance')
@login_required
def performance_screen():
    if not can_view_di_performance(current_user):
        abort(403)

    view, period_key = _resolve_view_and_period()
    rollup = snapshots.get_period_rollup(view, period_key)

    return render_template(
        'digital_innovation/performance.html',
        project=default_project(),
        sidebar_projects=sidebar_projects(),
        can_view_performance=True,
        can_edit_templates=can_edit_di_templates(current_user),
        can_edit_board=can_edit_di_board(current_user),
        view=view,
        view_labels=periods.PERIOD_VIEW_LABELS,
        period_key=period_key,
        rollup=rollup,
        currency=costs.get_settings().currency,
        prev_period=periods.shift_period(view, period_key, -1),
        next_period=periods.shift_period(view, period_key, 1),
    )


@digital_innovation_bp.route('/performance/export')
@login_required
def export_performance():
    """Streams the currently-viewed period's rollup as an .xlsx download
    — see lib/excel_export.py for the workbook itself. Honours the same
    view/period querystring as the page itself (falling back the same
    way _resolve_view_and_period() always does), so exporting from
    Monthly or a past period exports what's actually on screen."""
    if not can_view_di_performance(current_user):
        abort(403)

    view, period_key = _resolve_view_and_period()
    rollup = snapshots.get_period_rollup(view, period_key)
    workbook = build_performance_workbook(rollup, costs.get_settings().currency)

    filename = f"di_performance_{view}_{period_key}.xlsx"
    return send_file(
        workbook,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )
