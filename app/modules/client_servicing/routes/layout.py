"""
Saves per-user column widths and order for the Client Servicing table,
auto-saved (debounced client-side) as the user resizes or reorders. One
UserTableLayout row per (user, TABLE_KEY from table.py).
"""
from flask import request, jsonify
from flask_login import login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import UserTableLayout

from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.client_servicing.lib.access import require_cs
from app.modules.client_servicing.routes.blueprint import client_servicing_bp
from app.modules.client_servicing.routes.table import TABLE_KEY


@client_servicing_bp.route('/layout', methods=['POST'])
@login_required
@require_cs
def save_layout():
    # Emulation-aware: an admin previewing as someone saves that person's layout.
    actor = effective_user()

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
