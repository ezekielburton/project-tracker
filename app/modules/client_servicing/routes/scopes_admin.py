"""
CS Scope option list. Full CRUD needs manage_scopes (Admin Panel "CS Scopes"
tab); quick_add_scope is the table's inline "+ Add scope" behind require_cs.
Scopes are deactivated, never deleted, so rows keep their scope. Quick-add
reactivates a deactivated name so it never returns an unusable id.
"""
from flask import request, jsonify, abort
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import can

from app.modules.client_servicing.models import ClientServicingScope
from app.modules.client_servicing.lib.access import require_cs
from app.modules.client_servicing.routes.blueprint import client_servicing_bp


def _serialize(scope):
    return {'id': scope.id, 'name': scope.name, 'active': scope.active}


@client_servicing_bp.route('/scopes', methods=['GET'])
@login_required
def list_scopes():
    # Real user, not emulated: an admin previewing as someone keeps admin tools.
    if not can('manage_scopes', current_user):
        abort(403)
    scopes = ClientServicingScope.query.order_by(ClientServicingScope.name).all()
    return jsonify([_serialize(s) for s in scopes])


@client_servicing_bp.route('/scopes', methods=['POST'])
@login_required
def create_scope():
    # Real user, not emulated: an admin previewing as someone keeps admin tools.
    if not can('manage_scopes', current_user):
        abort(403)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if ClientServicingScope.query.filter_by(name=name).first():
        return jsonify({'error': 'Already exists'}), 409

    scope = ClientServicingScope(name=name, active=True)  # pyright: ignore[reportCallIssue]
    db.session.add(scope)
    db.session.commit()
    return jsonify(_serialize(scope))


@client_servicing_bp.route('/scopes/<int:scope_id>', methods=['PATCH'])
@login_required
def update_scope(scope_id):
    # Real user, not emulated: an admin previewing as someone keeps admin tools.
    if not can('manage_scopes', current_user):
        abort(403)
    scope = ClientServicingScope.query.get_or_404(scope_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        clash = ClientServicingScope.query.filter(
            ClientServicingScope.name == name, ClientServicingScope.id != scope.id
        ).first()
        if clash:
            return jsonify({'error': 'Already exists'}), 409
        scope.name = name

    if 'active' in data:
        scope.active = bool(data.get('active'))

    db.session.commit()
    return jsonify(_serialize(scope))


@client_servicing_bp.route('/scopes/quick-add', methods=['POST'])
@login_required
@require_cs
def quick_add_scope():
    # Page gate only (require_cs, emulation-aware), unlike the admin CRUD above.
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    existing = ClientServicingScope.query.filter_by(name=name).first()
    if existing:
        if not existing.active:
            existing.active = True
            db.session.commit()
        return jsonify(_serialize(existing))

    scope = ClientServicingScope(name=name, active=True)  # pyright: ignore[reportCallIssue]
    db.session.add(scope)
    db.session.commit()
    return jsonify(_serialize(scope))
