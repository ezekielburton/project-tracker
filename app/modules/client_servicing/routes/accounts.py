"""
Client Servicing — Accounts. Every job grouped by client or CS lead.
Read-only; the figures come from lib/accounts.py, the saved view from
lib/accounts_state.py.
"""
from flask import jsonify, render_template, request
from flask_login import login_required

from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.client_servicing.lib.access import require_cs
from app.modules.client_servicing.lib import accounts as accounts_lib
from app.modules.client_servicing.lib import accounts_state
from app.modules.client_servicing.routes.blueprint import client_servicing_bp


def _id_arg(name):
    """A positive id from the query string, else None (no filter)."""
    try:
        value = int(request.args.get(name, ''))
    except ValueError:
        return None
    return value if value > 0 else None


@client_servicing_bp.route('/accounts')
@login_required
@require_cs
def accounts():
    actor = effective_user()
    state = accounts_state.load_state(actor)
    view = accounts_lib.accounts_view(
        actor,
        # No ?group= (e.g. from the rail) reopens the user's last view.
        group=request.args.get('group') or state['group'],
        client_id=_id_arg('client'),
        lead_id=_id_arg('lead'),
        month=accounts_lib.parse_month(request.args.get('month')),
    )
    return render_template('client_servicing/accounts.html', state=state,
                           open_keys=state['open'][view['group']], **view)


@client_servicing_bp.route('/accounts/state', methods=['POST'])
@login_required
@require_cs
def save_accounts_state():
    """Save the user's last Group by and open groups. Emulation-aware."""
    data = request.get_json(silent=True)
    if not accounts_state.is_valid(data):
        return jsonify({'error': 'invalid payload'}), 400
    accounts_state.save_state(effective_user(), data)
    return jsonify({'status': 'ok'})
