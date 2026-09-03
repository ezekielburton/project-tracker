# Digital Innovation — the Archive screen: closed and archived projects,
# each reopenable, closed ones also archivable one step further. Same
# thin-HTTP-layer discipline as routes/templates.py, but there's no lib/
# file behind this one — the actual state changes (close/archive/reopen)
# already live in routes/projects.py; this file only renders the list.

from flask import render_template
from flask_login import login_required, current_user

from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.lib.access import can_view_di_performance, can_edit_di_templates, can_edit_di_board
from app.modules.digital_innovation.lib.board_data import sidebar_projects, default_project, closed_projects, archived_projects


@digital_innovation_bp.route('/archive')
@login_required
def archive_screen():
    return render_template(
        'digital_innovation/archive.html',
        project=default_project(),
        sidebar_projects=sidebar_projects(),
        can_view_performance=can_view_di_performance(current_user),
        can_edit_templates=can_edit_di_templates(current_user),
        can_edit_board=can_edit_di_board(current_user),
        closed_projects=closed_projects(),
        archived_projects=archived_projects(),
    )


@digital_innovation_bp.route('/archive/lists', methods=['GET'])
@login_required
def archive_lists_fragment():
    """Re-renders _archive_lists.html fresh — called on every DI-wide
    live SSE ping (see digital_innovation_archive.js) so a project
    someone else just closed, archived or reopened shows up here without
    a manual reload. No extra access gate: viewing Archive has never been
    restricted (same as Board), and this is purely a read — the actual
    close/archive/reopen actions stay gated by can_edit_di_board over in
    routes/projects.py, unchanged."""
    return render_template(
        'digital_innovation/_archive_lists.html',
        can_edit_board=can_edit_di_board(current_user),
        closed_projects=closed_projects(),
        archived_projects=archived_projects(),
    )
