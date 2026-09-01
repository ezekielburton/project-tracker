# The Digital Innovation board — the Trello-style pipeline view. Feature
# creation, step ticking and the advance/close flows are Phase 2b; this
# renders the board read-only plus the project switcher.

from flask import render_template, abort
from flask_login import login_required, current_user
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject, DI_STAGES, DI_STAGE_LABELS, DI_STAGE_COLOURS
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project, build_board_context
from app.modules.digital_innovation.lib.access import can_view_di_performance


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
    return _render_board(project)


def _render_board(project):
    return render_template(
        'digital_innovation/board.html',
        project=project,
        sidebar_projects=sidebar_projects(),
        can_view_performance=can_view_di_performance(current_user),
        stages=DI_STAGES,
        stage_labels=DI_STAGE_LABELS,
        stage_colours=DI_STAGE_COLOURS,
        **build_board_context(project),
    )
