# Feature routes: create, detail modal, and step actions (tick, add, delete,
# move stage, close, reopen). The rules live in lib/step_engine.py; each route loads
# the record, calls the engine, commits (or rolls back on ValueError) and
# returns the detail fragment.

from datetime import datetime

from flask import request, jsonify, abort, render_template
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiFeature, DiFeatureStep, DiProject, DI_STAGES
from app.modules.digital_innovation.lib import step_engine
from app.modules.digital_innovation.lib.feature_detail import build_feature_detail_context
from app.modules.digital_innovation.lib.access import can_edit_di_board, can_view_di_project


def _render_feature_detail(feature):
    """The feature-detail modal fragment. Every route here returns this.
    can_edit_board decides whether the interactive controls are rendered at all."""
    context = build_feature_detail_context(feature)
    return render_template(
        'digital_innovation/_feature_detail.html',
        feature=feature,
        project=feature.project,
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

    starting_stage = (data.get('starting_stage') or '').strip() or None
    if starting_stage and starting_stage not in DI_STAGES:
        return jsonify({'error': f"'{starting_stage}' isn't a valid starting stage."}), 400

    try:
        feature = step_engine.create_feature(
            project, name, projected_date=projected_date, starting_stage=starting_stage,
        )
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return jsonify({'id': feature.id, 'name': feature.name, 'status': feature.status}), 201


@digital_innovation_bp.route('/features/<int:feature_id>')
@login_required
def feature_detail(feature_id):
    """The feature-detail modal fragment for digital_innovation_board.js."""
    feature = DiFeature.query.get_or_404(feature_id)
    # A feature is visible only if its project is.
    if not can_view_di_project(current_user, feature.project):
        abort(403)
    return _render_feature_detail(feature)


@digital_innovation_bp.route('/features/<int:feature_id>/steps', methods=['POST'])
@login_required
def add_feature_step(feature_id):
    """Adds a step to the feature's current stage."""
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


@digital_innovation_bp.route('/features/<int:feature_id>/move', methods=['POST'])
@login_required
def move_feature_stage(feature_id):
    """Moves a feature to any stage, forward or backward, with no completion
    gate."""
    _require_board_write_access()
    feature = DiFeature.query.get_or_404(feature_id)

    data = request.get_json(silent=True) or {}
    target_stage = (data.get('stage') or '').strip()
    if not target_stage:
        return jsonify({'error': 'Target stage is required.'}), 400

    try:
        step_engine.move_to_stage(feature, target_stage)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_feature_detail(feature)


@digital_innovation_bp.route('/features/<int:feature_id>/close', methods=['POST'])
@login_required
def close_feature_route(feature_id):
    """Closes a feature. Only allowed in the last stage with every step
    done; step_engine.close_feature() does not check this itself."""
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


@digital_innovation_bp.route('/features/<int:feature_id>/reopen', methods=['POST'])
@login_required
def reopen_feature_route(feature_id):
    """Reopens a closed feature into the last stage. Same gate as close."""
    _require_board_write_access()
    feature = DiFeature.query.get_or_404(feature_id)

    try:
        step_engine.reopen_feature(feature)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

    return _render_feature_detail(feature)
