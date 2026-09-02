# Digital Innovation — feature (card) management. Creation, the detail
# view and every step interaction (tick/add/delete step, advance, close)
# live here. Every rule about how a feature actually moves lives in
# lib/step_engine.py (brain A) — this file is just the HTTP layer on top
# of it: pull the record(s), call the engine, commit or roll back on a
# ValueError, and hand back the same rendered fragment the initial GET
# uses so the modal always ends up showing the feature's true state.

from datetime import datetime

from flask import request, jsonify, abort, render_template
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiFeature, DiFeatureStep, DiProject, DI_STAGES
from app.modules.digital_innovation.lib import step_engine
from app.modules.digital_innovation.lib.feature_detail import build_feature_detail_context
from app.modules.digital_innovation.lib.access import can_view_di_performance, can_edit_di_board


def _render_feature_detail(feature):
    """The one place that turns a feature into the modal's HTML fragment —
    used by the initial GET and by every mutating route below, so a tick,
    an add, a delete, an advance or a close all leave the modal showing
    exactly what the GET route would show for that same feature.

    can_view_costs gates the footer's cost/charge/profit note — reuses the
    same admin/management choke point Performance and Cost breakdown
    already gate through (lib/access.py), so adding a role to any of the
    three is the one change in that one file. can_edit_board gates every
    interactive control (tick a step, delete it, the add-step form, the
    advance/close buttons) — the board is view-only for anyone it's False
    for, so the template renders those controls at all only when it's
    True, rather than rendering-then-disabling them."""
    context = build_feature_detail_context(feature)
    return render_template(
        'digital_innovation/_feature_detail.html',
        feature=feature,
        project=feature.project,
        can_view_costs=can_view_di_performance(current_user),
        can_edit_board=can_edit_di_board(current_user),
        **context,
    )


def _require_board_write_access():
    if not can_edit_di_board(current_user):
        abort(403)


@digital_innovation_bp.route('/<int:di_project_id>/features', methods=['POST'])
@login_required
def create_feature(di_project_id):
    _require_board_write_access()

    project = DiProject.query.filter_by(id=di_project_id, lifecycle='active').first()
    if not project:
        abort(404)

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required.'}), 400

    projected_date = None
    raw_date = (data.get('projected_date') or '').strip()
    if raw_date:
        try:
            projected_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Projected date must be a valid date (YYYY-MM-DD).'}), 400

    feature = step_engine.create_feature(project, name, projected_date=projected_date)
    db.session.commit()

    return jsonify({'id': feature.id, 'name': feature.name, 'status': feature.status}), 201


@digital_innovation_bp.route('/features/<int:feature_id>')
@login_required
def feature_detail(feature_id):
    """Returns the feature-detail modal's content as a rendered HTML
    fragment — digital_innovation_board.js drops it straight into the
    modal body."""
    feature = DiFeature.query.get_or_404(feature_id)
    return _render_feature_detail(feature)


@digital_innovation_bp.route('/features/<int:feature_id>/steps', methods=['POST'])
@login_required
def add_feature_step(feature_id):
    """Adds a step to the feature's current stage — the checklist's
    "add a step" input, and also how the Implementation-stage "add
    another step" choice is handled (same action, step_engine.add_step
    doesn't distinguish the two)."""
    _require_board_write_access()
    feature = DiFeature.query.get_or_404(feature_id)

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    details = (data.get('details') or '').strip() or None
    if not title:
        return jsonify({'error': 'Step title is required.'}), 400

    try:
        step_engine.add_step(feature, title, details=details)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_feature_detail(feature)


@digital_innovation_bp.route('/steps/<int:step_id>/tick', methods=['POST'])
@login_required
def tick_feature_step(step_id):
    _require_board_write_access()
    step = DiFeatureStep.query.get_or_404(step_id)
    feature = step.feature

    data = request.get_json(silent=True) or {}
    done = bool(data.get('done', True))

    try:
        step_engine.tick_step(step, done=done)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_feature_detail(feature)


@digital_innovation_bp.route('/steps/<int:step_id>', methods=['DELETE'])
@login_required
def delete_feature_step(step_id):
    _require_board_write_access()
    step = DiFeatureStep.query.get_or_404(step_id)
    feature = step.feature

    try:
        step_engine.delete_step(step)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_feature_detail(feature)


@digital_innovation_bp.route('/features/<int:feature_id>/advance', methods=['POST'])
@login_required
def advance_feature(feature_id):
    _require_board_write_access()
    feature = DiFeature.query.get_or_404(feature_id)

    try:
        step_engine.advance_stage(feature)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_feature_detail(feature)


@digital_innovation_bp.route('/features/<int:feature_id>/close', methods=['POST'])
@login_required
def close_feature_route(feature_id):
    """Closes an Implementation-stage feature once every step is done —
    the "close this feature" choice offered alongside "add another step".
    step_engine.close_feature() itself doesn't gate on stage/completeness
    (it's a plain state-set used e.g. by tests), so that check belongs
    here, at the HTTP boundary."""
    _require_board_write_access()
    feature = DiFeature.query.get_or_404(feature_id)

    if feature.status != DI_STAGES[-1] or not step_engine.is_stage_complete(feature):
        return jsonify({'error': 'Finish all Implementation steps before closing this feature.'}), 400

    try:
        step_engine.close_feature(feature)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_feature_detail(feature)
