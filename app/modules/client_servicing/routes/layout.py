"""
Per-user column widths (and order, once reorder writes to it) for the
Client Servicing table. Silent, personal, auto-saved as the user drags,
debounced client-side. Uses the shared UserTableLayout model and the
one-row-per-(user, table_key) pattern the Projects page uses; TABLE_KEY
(table.py) is this module's key. Kept in this module rather than the
Projects generic /layout route because UserTableLayout is a core/shared
model — writing to it belongs with the table that owns the layout.
"""
from flask import request, jsonify, abort
from flask_login import login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import UserTableLayout

from app.modules.client_servicing.lib.access import can_access_client_servicing, _effective_user
from app.modules.client_servicing.routes.blueprint import client_servicing_bp
from app.modules.client_servicing.routes.table import TABLE_KEY


@client_servicing_bp.route('/layout', methods=['POST'])
@login_required
def save_layout():
    # An admin previewing as someone else saves (and later sees) that
    # person's column layout, not the admin's.
    actor = _effective_user()
    if not can_access_client_servicing(actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    layout = data.get('layout')
    if not isinstance(layout, list) or not layout:
        return jsonify({'error': 'invalid payload'}), 400
    for entry in layout:
        if not isinstance(entry, dict) or 'key' not in entry or 'width' not in entry:
            return jsonify({'error': 'invalid payload'}), 400

    row = UserTableLayout.query.filter_by(user_id=actor.id, table_key=TABLE_KEY).first()
    if row:
        row.layout = layout
    else:
        row = UserTableLayout(user_id=actor.id, table_key=TABLE_KEY, layout=layout)
        db.session.add(row)
    db.session.commit()

    return jsonify({'status': 'ok'})
