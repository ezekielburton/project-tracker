"""
Client Servicing — Installation Calendar. Month grid + Agenda, both driven
by each project's installation_date and the effective CS status/risk. Own
route file, same one-concern-per-file convention as the other CS routes.
"""
from datetime import date

from flask import render_template, request, abort
from flask_login import login_required

from app.modules.client_servicing.lib.access import can_access_client_servicing, _effective_user
from app.modules.client_servicing.lib.calendar import (
    month_grid, agenda_groups, build_install, RISK_OPTIONS,
)
from app.modules.client_servicing.lib.status import CS_STATUS_OPTIONS
from app.modules.client_servicing.routes.blueprint import client_servicing_bp
from app.modules.client_servicing.routes.table import _base_projects


def _require_access():
    if not can_access_client_servicing(_effective_user()):
        abort(403)


def _parse_month(raw):
    """?month=YYYY-MM -> (year, month); today's month on anything invalid."""
    today = date.today()
    if raw:
        try:
            y, m = raw.split('-')
            y, m = int(y), int(m)
            if 1 <= m <= 12:
                return y, m
        except (ValueError, AttributeError):
            pass
    return today.year, today.month


def _shift_month(year, month, delta):
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, idx % 12 + 1


def _default_selected(weeks, today):
    """Which day the drawer opens on: today if it has installs, else the
    first in-month day that does."""
    for wk in weeks:
        for day in wk:
            if day['is_today'] and day['installs']:
                return day['date']
    for wk in weeks:
        for day in wk:
            if day['in_month'] and day['installs']:
                return day['date']
    return None


def _selected_day(weeks, target):
    for wk in weeks:
        for day in wk:
            if day['date'] == target:
                return day
    return None


@client_servicing_bp.route('/calendar')
@login_required
def calendar():
    _require_access()
    today = date.today()
    if request.args.get('view') == 'agenda':
        groups, kpis = agenda_groups(_base_projects().all(), today)
        return render_template(
            'client_servicing/calendar_agenda.html',
            active_view='agenda', kpis=kpis, groups=groups,
            today=today, risk_options=RISK_OPTIONS, status_options=CS_STATUS_OPTIONS,
        )

    year, month = _parse_month(request.args.get('month'))
    weeks, kpis = month_grid(_base_projects().all(), year, month, today)
    prev_y, prev_m = _shift_month(year, month, -1)
    next_y, next_m = _shift_month(year, month, 1)
    selected = _default_selected(weeks, today)
    return render_template(
        'client_servicing/calendar.html',
        active_view='month', kpis=kpis, weeks=weeks, today=today,
        year=year, month=month,
        month_label=date(year, month, 1).strftime('%B %Y'),
        prev_month='%04d-%02d' % (prev_y, prev_m),
        next_month='%04d-%02d' % (next_y, next_m),
        this_month='%04d-%02d' % (today.year, today.month),
        selected_day=_selected_day(weeks, selected) if selected else None,
        risk_options=RISK_OPTIONS, status_options=CS_STATUS_OPTIONS,
    )


@client_servicing_bp.route('/calendar/day/<datestr>')
@login_required
def calendar_day(datestr):
    """Drawer fragment for one day — fetched when the user clicks a day cell."""
    _require_access()
    try:
        target = date.fromisoformat(datestr)
    except (TypeError, ValueError):
        abort(404)
    today = date.today()
    installs = [
        build_install(p, today)
        for p in _base_projects().filter_by(installation_date=target).all()
    ]
    installs.sort(key=lambda i: i['client'] or '')
    return render_template(
        'client_servicing/_calendar_drawer.html',
        day={'date': target, 'installs': installs, 'count': len(installs)},
        risk_options=RISK_OPTIONS,
    )
