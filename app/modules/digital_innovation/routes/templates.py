# The admin-only Edit Templates screen (the default step list each stage copies
# onto features) and Settings screen (Dev Time rate, currency). Thin HTTP layer
# over lib/template_admin.py and lib/costs.py; every route calls
# _require_template_access(), so both screens share one gate.

from flask import request, jsonify, abort, render_template
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiStepTemplate, DI_STAGES, DI_STAGE_LABELS, DI_STAGE_COLOURS
from app.modules.digital_innovation.lib import template_admin, costs
from app.modules.digital_innovation.lib.access import can_edit_di_templates, can_view_di_performance, can_edit_di_board, visible_di_projects
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
        sidebar_projects=visible_di_projects(current_user, sidebar_projects()),
        can_view_performance=can_view_di_performance(current_user),
        can_edit_templates=True,  # enforced by _require_template_access above
        can_edit_board=can_edit_di_board(current_user),
        stages=DI_STAGES,
        stage_labels=DI_STAGE_LABELS,
        stage_colours=DI_STAGE_COLOURS,
        stage_steps=template_admin.templates_by_stage(),
    )


def _render_templates_body():
    """The templates body fragment. Every mutating route returns this."""
    return render_template(
        'digital_innovation/_templates_body.html',
        stages=DI_STAGES,
        stage_labels=DI_STAGE_LABELS,
        stage_colours=DI_STAGE_COLOURS,
        stage_steps=template_admin.templates_by_stage(),
    )


@digital_innovation_bp.route('/templates/body', methods=['GET'])
@login_required
def templates_body_fragment():
    """The templates body fragment, re-fetched on each di_changes SSE ping
    (digital_innovation_templates.js). Same gate as the page."""
    _require_template_access()
    return _render_templates_body()


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


# ── Settings screen ──

@digital_innovation_bp.route('/settings')
@login_required
def settings_screen():
    _require_template_access()
    return render_template(
        'digital_innovation/settings.html',
        project=default_project(),
        sidebar_projects=visible_di_projects(current_user, sidebar_projects()),
        can_view_performance=can_view_di_performance(current_user),
        can_edit_templates=True,  # enforced by _require_template_access above
        can_edit_board=can_edit_di_board(current_user),
        settings=costs.get_settings(),
    )


@digital_innovation_bp.route('/settings', methods=['POST'])
@login_required
def save_settings():
    """Saves the rate and currency. A 400 carries `errors` (field -> message)
    for the inline messages; nothing is saved when any field fails."""
    _require_template_access()
    data = request.get_json(silent=True) or {}

    errors = costs.update_settings(data.get('dev_hourly_rate'), data.get('currency'))
    if errors:
        return jsonify({'error': next(iter(errors.values())), 'errors': errors}), 400

    db.session.commit()
    settings = costs.get_settings()
    return jsonify({'dev_hourly_rate': settings.dev_hourly_rate, 'currency': settings.currency})
