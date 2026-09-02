# Digital Innovation — "Edit Templates" screen: the admin-only page for
# managing the department-wide default step lists each stage seeds new
# features' checklists from. Every route here is a thin HTTP layer over
# lib/template_admin.py, same discipline as routes/features.py over
# lib/step_engine.py — access is gated once per route (not a decorator,
# since the check needs lib/access.py's emulation-aware resolution) via
# _require_template_access(), never an inline role check.

from flask import request, jsonify, abort, render_template
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiStepTemplate, DI_STAGES, DI_STAGE_LABELS, DI_STAGE_COLOURS
from app.modules.digital_innovation.lib import template_admin
from app.modules.digital_innovation.lib.access import can_edit_di_templates, can_view_di_performance, can_edit_di_board
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project


def _require_template_access():
    if not can_edit_di_templates(current_user):
        abort(403)


@digital_innovation_bp.route('/templates')
@login_required
def templates_screen():
    _require_template_access()
    return render_template(
        'digital_innovation/templates.html',
        project=default_project(),
        sidebar_projects=sidebar_projects(),
        can_view_performance=can_view_di_performance(current_user),
        can_edit_templates=True,  # already enforced above — this page couldn't have rendered otherwise
        can_edit_board=can_edit_di_board(current_user),
        stages=DI_STAGES,
        stage_labels=DI_STAGE_LABELS,
        stage_colours=DI_STAGE_COLOURS,
        stage_steps=template_admin.templates_by_stage(),
    )


def _render_templates_body():
    """The one place that turns the current template state into the
    swappable fragment — used by every mutating route below, so an add,
    an edit, a delete or a move all leave the screen showing exactly what
    a fresh load of templates_screen would show."""
    return render_template(
        'digital_innovation/_templates_body.html',
        stages=DI_STAGES,
        stage_labels=DI_STAGE_LABELS,
        stage_colours=DI_STAGE_COLOURS,
        stage_steps=template_admin.templates_by_stage(),
    )


@digital_innovation_bp.route('/templates/<stage>/steps', methods=['POST'])
@login_required
def add_template_step(stage):
    _require_template_access()
    if stage not in DI_STAGES:
        abort(404)

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    details = (data.get('details') or '').strip() or None
    if not title:
        return jsonify({'error': 'Step title is required.'}), 400

    template_admin.add_template_step(stage, title, details=details)
    db.session.commit()
    return _render_templates_body()


@digital_innovation_bp.route('/template-steps/<int:template_id>', methods=['POST'])
@login_required
def edit_template_step(template_id):
    _require_template_access()
    template = DiStepTemplate.query.get_or_404(template_id)

    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    details = (data.get('details') or '').strip() or None
    if not title:
        return jsonify({'error': 'Step title is required.'}), 400

    template_admin.edit_template_step(template, title, details=details)
    db.session.commit()
    return _render_templates_body()


@digital_innovation_bp.route('/template-steps/<int:template_id>', methods=['DELETE'])
@login_required
def delete_template_step(template_id):
    _require_template_access()
    template = DiStepTemplate.query.get_or_404(template_id)

    template_admin.delete_template_step(template)
    db.session.commit()
    return _render_templates_body()


@digital_innovation_bp.route('/template-steps/<int:template_id>/move', methods=['POST'])
@login_required
def move_template_step(template_id):
    _require_template_access()
    template = DiStepTemplate.query.get_or_404(template_id)

    data = request.get_json(silent=True) or {}
    direction = data.get('direction')
    if direction not in ('up', 'down'):
        return jsonify({'error': 'direction must be "up" or "down".'}), 400

    template_admin.move_template_step(template, direction)
    db.session.commit()
    return _render_templates_body()
