# Performance screen (needs view_di_performance): weekly, monthly and quarterly
# rollups and their Excel export. The logic lives in lib/periods.py and
# lib/snapshots.py.

from flask import render_template, request, abort, send_file
from flask_login import login_required, current_user

from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.lib.access import can_view_di_performance, can_edit_di_templates, can_edit_di_board, visible_di_projects
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project
from app.modules.digital_innovation.lib import periods, snapshots, costs
from app.modules.digital_innovation.lib.excel_export import build_performance_workbook


def _resolve_view_and_period():
    """(view, period_key) from the querystring, defaulting to the current
    week. An invalid value falls back to the current period, not a 400."""
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
        sidebar_projects=visible_di_projects(current_user, sidebar_projects()),
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


@digital_innovation_bp.route('/performance/table', methods=['GET'])
@login_required
def performance_table_fragment():
    """The performance table fragment for the current view/period, re-fetched
    on each di_changes SSE ping (digital_innovation_performance.js)."""
    if not can_view_di_performance(current_user):
        abort(403)

    view, period_key = _resolve_view_and_period()
    rollup = snapshots.get_period_rollup(view, period_key)

    return render_template(
        'digital_innovation/_performance_table.html',
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
    """Downloads the rollup for the view/period in the querystring as .xlsx,
    matching what is on screen."""
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
