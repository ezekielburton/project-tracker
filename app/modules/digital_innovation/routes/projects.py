# Digital Innovation — project (board) management. Only creation lands here
# in Phase 2a; close/archive (with the is_permanent guard), the Incoming
# tray and the system-project link picker are Phase 2c-2e.

from flask import request, jsonify
from flask_login import login_required
from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
from app.modules.digital_innovation.models import DiProject

# Rotation the board's colored project dots cycle through on creation —
# same names as the app's existing .status-pill--<name> classes (see
# DI_STAGE_COLOURS in models.py), so no new colour-picker UI is needed for
# this phase and every dot is already dark-mode-tinted for free.
_COLOUR_ROTATION = ['sky', 'clover', 'coral', 'lavender', 'canary', 'sage', 'oak', 'poppy', 'salmon']


@digital_innovation_bp.route('/projects', methods=['POST'])
@login_required
def create_project():
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
