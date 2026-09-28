# Board management: create, set track, close/archive/reopen, and linking a
# board to a shared Project (search + set/clear).

from datetime import datetime

from flask import request, jsonify, abort
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject, DI_PROJECT_TRACKS
from app.modules.digital_innovation.lib.access import can_edit_di_board

# Colours new boards cycle through. Names must match the shared
# .status-pill--<name> classes, like DI_STAGE_COLOURS.
_COLOUR_ROTATION = ['sky', 'clover', 'coral', 'lavender', 'canary', 'sage', 'oak', 'poppy', 'salmon']


def _require_board_write_access():
    if not can_edit_di_board(current_user):
        abort(403)


def _permanent_guard(project):
    """None, or a 400 response if `project` is the permanent board, which
    can never be closed or archived (admins included)."""
    if project.is_permanent:
        return jsonify({'error': 'This project is permanent and cannot be closed or archived.'}), 400
    return None


@digital_innovation_bp.route('/projects', methods=['POST'])
@login_required
def create_project():
    _require_board_write_access()

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required.'}), 400

    # Defaults to 'internal'.
    track = (data.get('track') or '').strip() or 'internal'
    if track not in DI_PROJECT_TRACKS:
        return jsonify({'error': f"Track must be one of: {', '.join(DI_PROJECT_TRACKS)}."}), 400

    existing_count = DiProject.query.filter_by(lifecycle='active').count()
    project = DiProject(
        name=name,
        lifecycle='active',
        track=track,
        colour=_COLOUR_ROTATION[existing_count % len(_COLOUR_ROTATION)],
    )
    db.session.add(project)
    db.session.commit()

    return jsonify({
        'id': project.id, 'name': project.name, 'colour': project.colour, 'track': project.track,
    }), 201


@digital_innovation_bp.route('/projects/<int:project_id>/track', methods=['PATCH'])
@login_required
def update_project_track(project_id):
    """Sets a board's internal/external track. This only relabels the
    management_review stage; no feature's status or steps change."""
    _require_board_write_access()
    project = DiProject.query.get_or_404(project_id)

    track = (request.get_json(silent=True) or {}).get('track')
    if not isinstance(track, str) or track.strip() not in DI_PROJECT_TRACKS:
        return jsonify({'error': f"Track must be one of: {', '.join(DI_PROJECT_TRACKS)}."}), 400

    project.track = track.strip()
    db.session.commit()

    return jsonify({'id': project.id, 'track': project.track})


@digital_innovation_bp.route('/projects/<int:project_id>/close', methods=['POST'])
@login_required
def close_project(project_id):
    """active -> closed: leaves the sidebar and appears on the Archive screen."""
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
    """closed -> archived. Only a closed project can be archived."""
    _require_board_write_access()
    project = DiProject.query.filter_by(id=project_id, lifecycle='closed').first()
    if not project:
        abort(404)

    guard = _permanent_guard(project)  # defensive: a permanent board is never closed
    if guard:
        return guard

    project.lifecycle = 'archived'
    db.session.commit()

    return jsonify({'id': project.id, 'lifecycle': project.lifecycle})


@digital_innovation_bp.route('/projects/<int:project_id>/reopen', methods=['POST'])
@login_required
def reopen_project(project_id):
    """closed or archived -> active. Clears closed_at."""
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
    """Type-to-search for the link picker (#di-link-project-modal in
    board.html). Matches name or client; needs 2+ characters; max 20."""
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
    """Sets or clears DiProject.linked_project_id. The permanent board can
    never be linked (400)."""
    _require_board_write_access()
    project = DiProject.query.get_or_404(project_id)

    if project.is_permanent:
        return jsonify({'error': 'This project is permanent and cannot be linked to a system project.'}), 400

    body = request.get_json(silent=True) or {}
    # A null or missing linked_project_id clears the link.
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
