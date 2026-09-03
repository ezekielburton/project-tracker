"""
Client Servicing — Calendar section. Own route file, same
one-concern-per-file convention as the other CS routes. Empty placeholder
for now — a real, clickable page, built out later.
"""
from flask import render_template, abort
from flask_login import login_required

from app.modules.client_servicing.lib.access import can_access_client_servicing, _effective_user
from app.modules.client_servicing.routes.blueprint import client_servicing_bp


@client_servicing_bp.route('/calendar')
@login_required
def calendar():
    if not can_access_client_servicing(_effective_user()):
        abort(403)
    return render_template('client_servicing/calendar.html')
