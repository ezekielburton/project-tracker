"""
Client Servicing — Dashboard, the module's landing page. Aggregation lives
in lib/dashboard.py; these routes only gate access and render.
"""
from flask import render_template
from flask_login import login_required

from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.client_servicing.lib.access import require_cs
from app.modules.client_servicing.lib.dashboard import dashboard_context
from app.modules.client_servicing.routes.blueprint import client_servicing_bp


@client_servicing_bp.route('/')
@login_required
@require_cs
def index():
    actor = effective_user()
    return render_template('client_servicing/dashboard.html', **dashboard_context(actor))


@client_servicing_bp.route('/dashboard-panels')
@login_required
@require_cs
def dashboard_panels():
    """Panels fragment for the SSE live refresh; client_servicing_dashboard.js
    fetches it and swaps it in."""
    actor = effective_user()
    return render_template('client_servicing/_dashboard_panels.html', **dashboard_context(actor))