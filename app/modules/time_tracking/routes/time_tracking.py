# Time-tracking page: business hours per project and deliverable, by status.
# The math lives in logic.py.

from flask import Blueprint, render_template, abort
from flask_login import login_required
from app.modules.core.shared.lib.utils import get_actor
from app.modules.time_tracking.logic import build_time_tracking_rows
from app.modules.core.shared.lib.capabilities import can

time_tracking_bp = Blueprint('time_tracking', __name__, template_folder='../templates')


@time_tracking_bp.route('/time-tracking')
@login_required
def index():
    """Time-tracking page. Checks get_actor() so it is emulation-aware: an
    admin emulating a role without view_time_reports gets a 403."""
    actor = get_actor()
    if not can('view_time_reports', actor):
        abort(403)

    return render_template('time_tracking/index.html', rows=build_time_tracking_rows())
