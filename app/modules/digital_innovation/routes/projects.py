# Digital Innovation — project (board) management: creation, the three
# lifecycle actions (close, archive, reopen), and the system-project link
# (search + set/clear) — linking a DI project to a real projects-module
# Project so a future management dashboard can roll DI hours/profit up
# into it (see services/rollup.py, not yet built).

from datetime import datetime

from flask import request, jsonify, abort
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject
from app.modules.digital_innovation.lib.access import can_edit_di_board

# Rotation the board's colored project dots cycle through on creation —
# same names as the app's existing .status-pill--<name> classes (see
# DI_STAGE_COLOURS in models.py), so no new colour-picker UI is needed for
# this phase and every dot is already dark-mode-tinted for free.
_COLOUR_ROTATION = ['sky', 'clover', 'coral', 'lavender', 'canary', 'sage', 'oak', 'poppy', 'salmon']


def _require_board_write_access():
    if not can_edit_di_board(current_user):
        abort(403)


def _permanent_guard(project):
    """None if `project` isn't permanent; otherwise the (response, status)
    the route should return immediately. The seeded OVP board can never be
    closed or archived — whatever the UI does, whoever's asking, admin
    included — so this is checked in the two lifecycle routes below even
    though the UI never renders the controls for it either."""
    if project.is_permanent:
        return jsonify({'error': 'This project is permanent and cannot be closed or archived.'}), 400
    return None


@digital_innovation_bp.route('/projects', methods=['POST'])
@login_required
def create_project():
    _require_board_write_access()

    name = (request.get_json(silent=True) or {}).get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required.'}), 400

    existing_count = DiProject.query.filter_by(lifecycle='active').count()
    project = DiProject(
        name=name,
        lifecycle='active',
        colour=_COLOUR_ROTATION[existing_count % len(_COLOUR_ROTATION)],
    )
    db.session.add(project)
    db.session.commit()

    return jsonify({'id': project.id, 'name': project.name, 'colour': project.colour}), 201


@digital_innovation_bp.route('/projects/<int:project_id>/close', methods=['POST'])
@login_required
def close_project(project_id):
    """active -> closed. Drops off the active sidebar; the project shows
    up on the Archive screen instead, still reopenable from there."""
    _require_board_write_access()
    project = DiProject.query.filter_by(id=project_id, lifecycle='active').first()
    if not project:
        abort(404)

    guard = _permanent_guard(project)
    if guard:
        return guard

    project.lifecycle = 'closed'
    project.closed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'id': project.id, 'lifecycle': project.lifecycle})


@digital_innovation_bp.route('/projects/<int:project_id>/archive', methods=['POST'])
@login_required
def archive_project(project_id):
    """closed -> archived — one step further, from the Archive screen.
    Only a closed project can be archived; an active one has to be closed
    first."""
    _require_board_write_access()
    project = DiProject.query.filter_by(id=project_id, lifecycle='closed').first()
    if not project:
        abort(404)

    guard = _permanent_guard(project)  # unreachable today (permanent stays active) — kept for defense-in-depth
    if guard:
        return guard

    project.lifecycle = 'archived'
    db.session.commit()

    return jsonify({'id': project.id, 'lifecycle': project.lifecycle})


@digital_innovation_bp.route('/projects/<int:project_id>/reopen', methods=['POST'])
@login_required
def reopen_project(project_id):
    """closed or archived -> active — the escape hatch, so closing or
    archiving a project is never a one-way door."""
    _require_board_write_access()
    project = DiProject.query.filter(
        DiProject.id == project_id,
        DiProject.lifecycle.in_(['closed', 'archived']),
    ).first()
    if not project:
        abort(404)

    project.lifecycle = 'active'
    project.closed_at = None
    db.session.commit()

    return jsonify({'id': project.id, 'lifecycle': project.lifecycle})


@digital_innovation_bp.route('/projects/search', methods=['GET'])
@login_required
def search_projects():
    """Type-to-search for the system-project link picker (see
    #di-link-project-modal in board.html). The shared Project table can
    run into the hundreds across the company, so unlike the short lists
    (e.g. Clients) the rest of the app renders as a plain <select>, this
    needs server-side filtering rather than dumping every option in a
    dropdown. Gated the same as the picker itself — only can_edit_di_board
    users ever see the control that calls this."""
    _require_board_write_access()

    query = (request.args.get('q') or '').strip()
    if len(query) < 2:
        return jsonify([])

    like = f'%{query}%'
    matches = (
        Project.query
        .filter(db.or_(Project.name.ilike(like), Project.client.ilike(like)))
        .order_by(Project.name)
        .limit(20)
        .all()
    )
    return jsonify([
        {'id': p.id, 'name': p.name, 'client': p.client}
        for p in matches
    ])


@digital_innovation_bp.route('/projects/<int:project_id>/link', methods=['PATCH'])
@login_required
def link_project(project_id):
    """Sets or clears DiProject.linked_project_id. board.html's "part of
    -> [project]" badge reads project.linked_project directly (the
    relationship already exists on the model) so no extra context is
    needed on the board route itself. The permanent OVP board is never
    linkable — it isn't "part of" any single client project — same
    object-level-guard shape as close/archive, a 400 not a 403 since it's
    a rule about the object, not about who's asking."""
    _require_board_write_access()
    project = DiProject.query.get_or_404(project_id)

    if project.is_permanent:
        return jsonify({'error': 'This project is permanent and cannot be linked to a system project.'}), 400

    body = request.get_json(silent=True) or {}
    # Key present with value null (JS "Clear link") vs. key absent both
    # clear the link; only a real id sets one — keeps the endpoint usable
    # for both "set" and "clear" without a separate DELETE route.
    target_id = body.get('linked_project_id')

    if target_id is None:
        project.linked_project_id = None
    else:
        target = Project.query.get(target_id)
        if not target:
            return jsonify({'error': 'Project not found.'}), 400
        project.linked_project_id = target.id

    db.session.commit()

    return jsonify({
        'id': project.id,
        'linked_project_id': project.linked_project_id,
        'linked_project_name': project.linked_project.name if project.linked_project else None,
    })
