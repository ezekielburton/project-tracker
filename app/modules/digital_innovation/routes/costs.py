# Digital Innovation — Cost breakdown view (restricted, see lib/access.py).
# Per-project cost ledger CRUD + Excel export. Every route here gates on
# can_view_di_performance — per Ezekiel (1 Sep 2026), add/delete access is
# the same gate as view access, so there's no separate "can edit costs"
# check anywhere in this file.

from datetime import datetime

from flask import request, jsonify, abort, render_template, send_file
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject, DiFeature, DiCostEntry, DI_COST_TYPES
from app.modules.digital_innovation.lib import costs
from app.modules.digital_innovation.lib.excel_export import build_cost_ledger_workbook
from app.modules.digital_innovation.lib.access import can_view_di_performance


def _require_cost_access():
    if not can_view_di_performance(current_user):
        abort(403)


def _render_cost_breakdown(project):
    """The one place that turns a project into the Cost breakdown modal's
    HTML fragment — used by the initial GET and by every mutating route
    below, mirroring routes/features.py's _render_feature_detail() choke
    point: an add or a delete always leaves the modal showing exactly
    what a fresh GET would show for that project."""
    summary = costs.cost_summary(project)
    return render_template(
        'digital_innovation/_cost_breakdown.html',
        project=project,
        summary=summary,
        features=project.features,
        settings=costs.get_settings(),
        cost_types=DI_COST_TYPES,
        type_labels=costs.DI_COST_TYPE_LABELS,
        today=datetime.utcnow().date().isoformat(),
    )


@digital_innovation_bp.route('/<int:project_id>/costs')
@login_required
def cost_breakdown(project_id):
    """Returns the Cost breakdown modal's content as a rendered HTML
    fragment. Deliberately no lifecycle filter, unlike the live board's
    routes — a closed or archived project's cost history is still worth
    reviewing, so this works for every project regardless of state."""
    _require_cost_access()
    project = DiProject.query.get_or_404(project_id)
    return _render_cost_breakdown(project)


@digital_innovation_bp.route('/<int:project_id>/costs', methods=['POST'])
@login_required
def add_cost_entry_route(project_id):
    _require_cost_access()
    project = DiProject.query.get_or_404(project_id)

    data = request.get_json(silent=True) or {}
    cost_type = (data.get('type') or '').strip()

    raw_date = (data.get('date') or '').strip()
    entry_date = None
    if raw_date:
        try:
            entry_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Date must be a valid date (YYYY-MM-DD).'}), 400

    description = data.get('description')

    amount = data.get('amount')
    if amount is not None:
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'Amount must be a number.'}), 400

    hours = data.get('hours')
    if hours is not None:
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            return jsonify({'error': 'Hours must be a number.'}), 400

    # Only Dev Time entries carry a feature — resolved here (not in
    # lib/costs.py) because looking up a DiFeature by id is HTTP-layer
    # work, same division of labour as step_engine's callers always
    # passing objects, never raw ids.
    feature = None
    if cost_type == 'dev_time':
        feature_id = data.get('feature_id')
        feature = DiFeature.query.filter_by(id=feature_id, di_project_id=project.id).first()
        if feature is None:
            return jsonify({'error': 'A feature is required for Dev Time entries.'}), 400

    try:
        costs.add_cost_entry(
            project, entry_date, cost_type,
            description=description, amount=amount, hours=hours, feature=feature,
        )
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_cost_breakdown(project)


@digital_innovation_bp.route('/costs/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_cost_entry_route(entry_id):
    _require_cost_access()
    entry = DiCostEntry.query.get_or_404(entry_id)
    project = entry.project  # backref — re-render needs to know which project's modal this belongs to

    costs.delete_cost_entry(entry)
    db.session.commit()

    return _render_cost_breakdown(project)


@digital_innovation_bp.route('/<int:project_id>/costs/export')
@login_required
def export_cost_ledger(project_id):
    """Streams the project's ledger as an .xlsx download — see
    lib/excel_export.py for the workbook itself."""
    _require_cost_access()
    project = DiProject.query.get_or_404(project_id)

    summary = costs.cost_summary(project)
    workbook = build_cost_ledger_workbook(project, summary)

    filename = f"{project.name.replace(' ', '_')}_cost_ledger.xlsx"
    return send_file(
        workbook,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename,
    )
