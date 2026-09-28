# The board page, plus the columns fragment used by the live refresh.

from flask import render_template, abort
from flask_login import login_required, current_user
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject, DI_STAGES, DI_STAGE_COLOURS, stage_label
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project, build_board_context, pending_intake_items
from app.modules.digital_innovation.lib.access import can_view_di_performance, can_edit_di_templates, can_edit_di_board, can_view_di_project, visible_di_projects


# strict_slashes=False so /digital-innovation/ (bookmarks, typed URLs) lands
# on the board instead of a 404.
@digital_innovation_bp.route('', strict_slashes=False)
@login_required
def index():
    # The permanent board is seeded by a migration, so there is always one.
    return _render_board(default_project())


@digital_innovation_bp.route('/<int:di_project_id>')
@login_required
def project_board(di_project_id):
    project = DiProject.query.filter_by(id=di_project_id, lifecycle='active').first()
    if not project:
        abort(404)
    # Every board except the permanent one needs view_all_di.
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
        # Track-aware, so external boards show 'Client Review'.
        stage_labels={s: stage_label(s, project.track) for s in DI_STAGES},
        stage_colours=DI_STAGE_COLOURS,
        # Empty on every board except the permanent one.
        pending_intake_items=pending_intake_items(project),
        **build_board_context(project),
    )


@digital_innovation_bp.route('/<int:project_id>/board/columns', methods=['GET'])
@login_required
def board_columns_fragment(project_id):
    """The board columns fragment, re-fetched on each di_changes SSE ping
    (digital_innovation_board.js diRefreshBoard). Same view gate as
    project_board."""
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
