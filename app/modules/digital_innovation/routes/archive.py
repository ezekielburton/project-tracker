# The Archive screen: closed and archived projects. Read-only; the
# close/archive/reopen actions live in routes/projects.py.

from flask import render_template
from flask_login import login_required, current_user

from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.lib.access import can_view_di_performance, can_edit_di_templates, can_edit_di_board, visible_di_projects
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project, closed_projects, archived_projects


@digital_innovation_bp.route('/archive')
@login_required
def archive_screen():
    # The permanent board is never closed, so a user without view_all_di
    # always sees an empty Archive.
    return render_template(
        'digital_innovation/archive.html',
        project=default_project(),
        sidebar_projects=visible_di_projects(current_user, sidebar_projects()),
        can_view_performance=can_view_di_performance(current_user),
        can_edit_templates=can_edit_di_templates(current_user),
        can_edit_board=can_edit_di_board(current_user),
        closed_projects=visible_di_projects(current_user, closed_projects()),
        archived_projects=visible_di_projects(current_user, archived_projects()),
    )


@digital_innovation_bp.route('/archive/lists', methods=['GET'])
@login_required
def archive_lists_fragment():
    """The archive lists fragment, re-fetched on each di_changes SSE ping.
    Filtered the same way as archive_screen."""
    return render_template(
        'digital_innovation/_archive_lists.html',
        can_edit_board=can_edit_di_board(current_user),
        closed_projects=visible_di_projects(current_user, closed_projects()),
        archived_projects=visible_di_projects(current_user, archived_projects()),
    )
