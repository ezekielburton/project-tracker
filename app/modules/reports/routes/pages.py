"""Admin → Reports pages: Generate, History and Recipients. Gated on the real
user, so an admin previewing as someone else keeps them."""
from flask import render_template, request
from flask_login import login_required

from app.modules.core.shared.lib.capabilities import require
from app.modules.core.shared.lib.timezone import dubai_today
from app.modules.reports.lib import pages
from app.modules.reports.routes.blueprint import reports_bp

GATE = 'admin_panel'


@reports_bp.route('')
@login_required
@require(GATE, real_user=True)
def generate_page():
    return render_template('reports/generate.html', **pages.generate_view(dubai_today()))


@reports_bp.route('/history')
@login_required
@require(GATE, real_user=True)
def history_page():
    return render_template('reports/history.html', **pages.history_view(request.args, dubai_today()))


@reports_bp.route('/recipients')
@login_required
@require(GATE, real_user=True)
def recipients_page():
    return render_template('reports/recipients.html', **pages.recipients_view())
