"""The dashboard's rail pages: the landing redirect and every page whose section
is not built yet. Each is gated by its capability and by being on the rail."""
from datetime import date

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.modules.core.shared.lib.capabilities import effective_user, require, require_api
from app.modules.core.shared.lib.utils import log_activity
from app.modules.core.shared.lib.month_grid import month_span, month_weeks
from app.modules.dashboard.lib import admin_pages
from app.modules.dashboard.lib.calendar import EVENT_KINDS, calendar_events_for, parse_day, parse_month
from app.modules.dashboard.lib.rails import PAGES, rail_for
from app.modules.dashboard.lib.shell import on_rail, page_context
from app.modules.dashboard.routes.dashboard import dashboard_bp
from app.modules.system.lib.job_list import BY_KEY as JOBS_BY_KEY
from app.modules.system.services import health
from app.modules.system.services.run_now import NotRunnable, request_run
from app.modules.system.services.snapshot import read_snapshot


def _placeholder(key):
    return render_template('dashboard/placeholder.html', **page_context(key))


@dashboard_bp.route('')
@login_required
@require('view_workspace')
def index():
    """Sends the person to the first page on their rail, keeping the query string."""
    landing = PAGES[rail_for(effective_user()).landing]
    return redirect(url_for(landing.endpoint, **request.args.to_dict()))


# ── Pages on the personal rails ──────────────────────────────────────────

@dashboard_bp.route('/calendar')
@login_required
@require('view_workspace')
@on_rail('calendar')
def calendar():
    """The shared calendar: a month of the person's events and the chosen day's list."""
    today = date.today()
    selected = parse_day(request.args.get('day'))
    if selected:
        year, month = selected.year, selected.month
    else:
        year, month = parse_month(request.args.get('month'), today)
        selected = today if (today.year, today.month) == (year, month) else date(year, month, 1)

    start, end = month_span(year, month)
    by_day = {}
    for event in calendar_events_for(effective_user(), start, end):
        by_day.setdefault(event['date'], []).append(event)

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    return render_template(
        'dashboard/calendar.html',
        **page_context('calendar'),
        weeks=month_weeks(year, month, today, by_day),
        month_label=date(year, month, 1).strftime('%B %Y'),
        prev_month=f'{prev_y:04d}-{prev_m:02d}',
        next_month=f'{next_y:04d}-{next_m:02d}',
        selected_day=selected,
        day_label=f'{selected:%A} {selected.day} {selected:%B}',
        day_events=by_day.get(selected, []),
        event_kinds=EVENT_KINDS,
        kind_labels={kind.key: kind.label for kind in EVENT_KINDS},
    )


@dashboard_bp.route('/my-projects')
@login_required
@require('view_workspace')
@on_rail('my_projects')
def my_projects():
    return _placeholder('my_projects')


@dashboard_bp.route('/site-visits')
@login_required
@require('view_workspace')
@on_rail('site_visits')
def site_visits():
    return _placeholder('site_visits')


@dashboard_bp.route('/approvals')
@login_required
@require('view_workspace')
@on_rail('approvals')
def approvals():
    return _placeholder('approvals')


@dashboard_bp.route('/my-clients')
@login_required
@require('view_workspace')
@on_rail('my_clients')
def my_clients():
    return _placeholder('my_clients')


@dashboard_bp.route('/assignments')
@login_required
@require('view_workspace')
@on_rail('assignments')
def assignments():
    return _placeholder('assignments')


@dashboard_bp.route('/team')
@login_required
@require('view_workspace')
@on_rail('team')
def team():
    return _placeholder('team')


# ── Department pages (Head of Department and Management) ─────────────────

@dashboard_bp.route('/design-workload')
@login_required
@require('view_department_overview')
@on_rail('design_workload')
def design_workload():
    return _placeholder('design_workload')


@dashboard_bp.route('/needs-attention')
@login_required
@require('view_department_overview')
@on_rail('needs_attention')
def needs_attention():
    return _placeholder('needs_attention')


# ── Management pages ─────────────────────────────────────────────────────

@dashboard_bp.route('/escalations')
@login_required
@require('view_management_dashboard')
@on_rail('escalations')
def escalations():
    return _placeholder('escalations')


@dashboard_bp.route('/delivery')
@login_required
@require('view_management_dashboard')
@on_rail('delivery')
def delivery():
    return _placeholder('delivery')


@dashboard_bp.route('/teams')
@login_required
@require('view_management_dashboard')
@on_rail('teams')
def teams():
    return _placeholder('teams')


@dashboard_bp.route('/clients')
@login_required
@require('view_management_dashboard')
@on_rail('clients')
def clients():
    return _placeholder('clients')


@dashboard_bp.route('/adoption')
@login_required
@require('view_management_dashboard')
@on_rail('adoption')
def adoption():
    return _placeholder('adoption')


# ── Admin system pages: the real admin only, even while viewing as someone ─

@dashboard_bp.route('/admin/overview')
@login_required
@require('admin_panel', real_user=True)
def admin_overview():
    """How OVP is doing: the status strip, what needs the admin, today's use and the
    next jobs. Needs attention comes with the page; the other cards load after."""
    attention = admin_pages.part_context('overview', 'attention')
    return render_template('dashboard/admin/overview.html', **page_context('system_overview'),
                           **attention)


@dashboard_bp.route('/admin/system')
@login_required
@require('admin_panel', real_user=True)
def admin_system():
    """The machine: host, storage, network, updates and the application. Every card loads after the page."""
    return render_template('dashboard/admin/system.html', **page_context('system'),
                           headline=health.freshness(read_snapshot()))


@dashboard_bp.route('/api/admin/<page>/<part>')
@login_required
@require('admin_panel', real_user=True)
def admin_part(page, part):
    """One card of an admin system page as HTML; the page loads and refreshes its cards here."""
    if part not in admin_pages.PARTS.get(page, {}):
        abort(404)
    return render_template(f'dashboard/admin/parts/{page}_{part}.html',
                           **admin_pages.part_context(page, part))


@dashboard_bp.route('/admin/database')
@login_required
@require('admin_panel', real_user=True)
def admin_database():
    return _placeholder('database')


@dashboard_bp.route('/admin/performance')
@login_required
@require('admin_panel', real_user=True)
def admin_performance():
    return _placeholder('performance')


@dashboard_bp.route('/admin/usage')
@login_required
@require('admin_panel', real_user=True)
def admin_usage():
    return _placeholder('usage')


@dashboard_bp.route('/admin/errors')
@login_required
@require('admin_panel', real_user=True)
def admin_errors():
    return _placeholder('errors')


@dashboard_bp.route('/admin/uptime')
@login_required
@require('admin_panel', real_user=True)
def admin_uptime():
    return _placeholder('uptime')


@dashboard_bp.route('/admin/jobs')
@login_required
@require('admin_panel', real_user=True)
def admin_jobs():
    return _placeholder('jobs')


@dashboard_bp.route('/api/admin/jobs/<job_key>/run', methods=['POST'])
@require_api('admin_panel', real_user=True)
def admin_job_run_now(job_key):
    """Start one listed job now; the run is recorded against the real admin."""
    if job_key not in JOBS_BY_KEY:
        return jsonify({'success': False, 'error': 'Unknown job'}), 404
    try:
        request_run(job_key, current_user.id, folder=current_app.config['RUN_NOW_DIR'])
    except NotRunnable:
        return jsonify({'success': False, 'error': 'This job can’t be started by hand'}), 400
    except OSError:
        return jsonify({'success': False, 'error': 'Could not reach the job runner'}), 503
    log_activity('job_run_now', f'Started {JOBS_BY_KEY[job_key].label} by hand',
                 user=current_user, entity_type='job', entity_name=job_key)
    return jsonify({'success': True, 'job': job_key})
