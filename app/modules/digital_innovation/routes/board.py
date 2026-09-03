# The Digital Innovation board — the Trello-style pipeline view: renders the
# board plus the project switcher. board_columns_fragment re-renders just the
# columns + closed-features strip for the board-wide live refresh.

from flask import render_template, abort
from flask_login import login_required, current_user
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject, DI_STAGES, DI_STAGE_COLOURS, stage_label
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project, build_board_context, pending_intake_items
from app.modules.digital_innovation.lib.access import can_view_di_performance, can_edit_di_templates, can_edit_di_board, can_view_di_project, visible_di_projects


@digital_innovation_bp.route('')
@login_required
def index():
    # default_project() always finds the permanent OVP board — seeded by
    # the migration and un-deletable — so there's no "no boards at all"
    # empty state to handle here.
    return _render_board(default_project())


@digital_innovation_bp.route('/<int:di_project_id>')
@login_required
def project_board(di_project_id):
    project = DiProject.query.filter_by(id=di_project_id, lifecycle='active').first()
    if not project:
        abort(404)
    # Visibility gate (lib/access.py): every board except the permanent OVP one
    # is restricted to admin/management/future digital_innovation — a designer
    # hitting a non-OVP board's URL directly gets a 403.
    if not can_view_di_project(current_user, project):
        abort(403)
    return _render_board(project)


def _render_board(project):
    return render_template(
        'digital_innovation/board.html',
        project=project,
        sidebar_projects=visible_di_projects(current_user, sidebar_projects()),
        can_view_performance=can_view_di_performance(current_user),
        can_edit_templates=can_edit_di_templates(current_user),
        can_edit_board=can_edit_di_board(current_user),
        stages=DI_STAGES,
        # Track-aware (stage_label) so a column header reads 'Client Review'
        # rather than 'Management Review' on an external board — computed once
        # per render.
        stage_labels={s: stage_label(s, project.track) for s in DI_STAGES},
        stage_colours=DI_STAGE_COLOURS,
        # Only the permanent OVP board ever has intake items attached
        # (services/intake.py always files against it), so this is an
        # empty list on every other board — cheap enough not to bother
        # gating the query itself on project.is_permanent.
        pending_intake_items=pending_intake_items(project),
        **build_board_context(project),
    )


@digital_innovation_bp.route('/<int:project_id>/board/columns', methods=['GET'])
@login_required
def board_columns_fragment(project_id):
    """Re-renders _board_columns.html fresh — called on every live SSE
    ping (see digital_innovation_board.js::diRefreshBoard) so the board
    reflects other users' feature moves, step ticks, new/closed features
    without a manual reload. No can_edit_board gate — this is a read — but still
    gated by can_view_di_project, the same visibility rule as project_board,
    just returning a fragment instead of the full page."""
    project = DiProject.query.filter_by(id=project_id, lifecycle='active').first()
    if not project:
        abort(404)
    if not can_view_di_project(current_user, project):
        abort(403)

    return render_template(
        'digital_innovation/_board_columns.html',
        project=project,
        stages=DI_STAGES,
        stage_colours=DI_STAGE_COLOURS,
        stage_labels={s: stage_label(s, project.track) for s in DI_STAGES},
        can_edit_board=can_edit_di_board(current_user),
        **build_board_context(project),
    )
