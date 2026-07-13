# app/routes/time_tracking.py
#
# New feature, own blueprint/JS/CSS per this project's established
# convention (every new feature gets a dedicated route file, JS file, and
# CSS file — see CLAUDE.md). Added 13 Jul 2026, per Ezekiel: "this card
# will open a different dashboard page, with its own table that shows
# each project + overall hours + hours in each state -> each deliverable
# for that project + overall hours + hours in each state."
#
# Management/admin only for now (per Ezekiel: "Management and admin can
# open the time tracking dashboard for now") — CS/Designer/Team Lead still
# see the Average Time TILE on the main dashboard, just can't click
# through to this breakdown page yet.
#
# All the actual business-hours/weekend-discard math lives in
# app/time_tracking_logic.py (pure functions, no Flask/DB writes) — this
# file is just the route: fetch scoped projects + deliverables, run each
# through that module, hand the result to the template.

from flask import Blueprint, render_template, abort
from flask_login import login_required
from app.utils import get_actor
from app.models import Project
from app.time_tracking_logic import compute_project_hours, compute_deliverable_hours

time_tracking_bp = Blueprint('time_tracking', __name__)


@time_tracking_bp.route('/time-tracking')
@login_required
def index():
    """
    One row per non-draft project, each carrying its own overall/by-status
    business-hours breakdown plus the same breakdown for every one of its
    (standard-brief) deliverables. Company-wide, not scoped to a
    particular CS lead's projects — this is a reporting page for
    management/admin, same "answer for everyone, not just me" reasoning
    _compute_project_stats()'s total_active uses (see dashboard.py).

    C&CM per-customer status history (ProjectCustomerStatusLog) is NOT
    included here — Ezekiel's ask was specifically "each project ... each
    deliverable", and standard-brief Deliverable rows are what that maps
    to. Worth a follow-up if C&CM customer-level breakdowns turn out to be
    wanted too.

    Access check made emulation-aware (13 Jul 2026, same-day follow-up,
    per Ezekiel: "it's not emulation aware") — was the shared
    @role_required('admin', 'management') decorator, which checks
    current_user directly (deliberately, for admin-only WRITE routes —
    see get_actor()'s docstring in app/utils.py). But this is a read-only
    reporting VIEW, not a write action, and the stat_avg_time.html tile
    that links here was fixed the same way in the same pass: an admin
    emulating a CS/Designer/Team Lead should see this page exactly as
    unreachable as that role would, matching what the now-static
    (non-link) tile already shows them. Replaced with a manual get_actor()
    check so the shared role_required decorator (used by plenty of
    genuine admin-only write routes elsewhere) didn't need to change
    behaviour for everyone else.
    """
    actor = get_actor()
    if actor.role not in ('admin', 'management'):
        abort(403)

    projects = Project.query.filter(Project.project_status != 'draft').order_by(Project.name).all()

    rows = []
    for p in projects:
        deliverables = []
        for d in p.project_deliverables:
            d_hours = compute_deliverable_hours(d)
            deliverables.append({
                'id': d.id,
                'name': d.name,
                'overall': d_hours['overall'],
                'by_status': d_hours['by_status'],
            })

        p_hours = compute_project_hours(p)
        rows.append({
            'id': p.id,
            'name': p.name,
            'overall': p_hours['overall'],
            'by_status': p_hours['by_status'],
            'deliverables': deliverables,
        })

    return render_template('time_tracking.html', rows=rows)
