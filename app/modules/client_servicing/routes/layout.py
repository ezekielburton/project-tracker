"""
Per-user column widths (and, once a later piece adds reorder, order) for
the Client Servicing table — Chunk 7. Silent, personal, auto-saved as the
user drags, debounced client-side. Uses the same shared UserTableLayout
model and one-row-per-(user, table_key) pattern the Projects page already
uses for its own tables; TABLE_KEY (in table.py) is this module's key.

Deliberately its own route here rather than a call to the Projects
module's existing generic /layout endpoint — same reasoning as Chunk 4's
mutations.py and Chunk 6's scopes_admin.py: UserTableLayout is a
core/shared model, so writing to it belongs in the module that owns the
table being laid out, not routed through another feature module's
blueprint.
"""
from flask import request, jsonify, abort
from flask_login import login_required, current_user

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import UserTableLayout

from app.modules.client_servicing.lib.access import can_access_client_servicing
from app.modules.client_servicing.routes.blueprint import client_servicing_bp
from app.modules.client_servicing.routes.table import TABLE_KEY


@client_servicing_bp.route('/layout', methods=['POST'])
@login_required
def save_layout():
    if not can_access_client_servicing(current_user):
        abort(403)

    data = request.get_json(silent=True) or {}
    layout = data.get('layout')
    if not isinstance(layout, list) or not layout:
        return jsonify({'error': 'invalid payload'}), 400
    for entry in layout:
        if not isinstance(entry, dict) or 'key' not in entry or 'width' not in entry:
            return jsonify({'error': 'invalid payload'}), 400

    row = UserTableLayout.query.filter_by(user_id=current_user.id, table_key=TABLE_KEY).first()
    if row:
        row.layout = layout
    else:
        row = UserTableLayout(user_id=current_user.id, table_key=TABLE_KEY, layout=layout)
        db.session.add(row)
    db.session.commit()

    return jsonify({'status': 'ok'})
