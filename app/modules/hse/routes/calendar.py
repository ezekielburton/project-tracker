"""
HSE calendar: Month and Agenda views, plus the day drawer.

Read-only: "Log it" hands off to the normal entry form, and no route here
writes a row. No SSE, since HSE has a single user; polling.js is the
pattern to follow if that changes.
"""
from datetime import date, timedelta

from flask import abort, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app.modules.core.shared.lib.capabilities import require
from app.modules.hse.lib.calendar import (
    AGENDA_DAYS, agenda_groups, day_summary, default_day, drawer_cards,
    grid_bounds, items_by_day, kpis, month_grid, parse_day, parse_month,
    shift_month, state_chips,
)
from app.modules.hse.lib.registers import HSE_REGISTERS
from app.modules.hse.lib.query import open_counts_by_register
from app.modules.hse.lib.rail import GROUP_LABELS, rail_items
from app.modules.hse.models import HseEntry, HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


def _schedules():
    return (HseSchedule.query
            .options(selectinload(HseSchedule.assets), selectinload(HseSchedule.owner))
            .all())


def _entries(start, end):
    """Every entry that could appear in the window, in one query: by filed
    date, due/expiry date, or occurrence date."""
    return (HseEntry.query
            .options(selectinload(HseEntry.asset),
                     selectinload(HseEntry.reported_by),
                     selectinload(HseEntry.assigned_to),
                     selectinload(HseEntry.subject),
                     # The drawer says who filed a done job and when.
                     selectinload(HseEntry.created_by))
            .filter(or_(
                HseEntry.entry_date.between(start, end),
                HseEntry.due_at.between(start, end),
                HseEntry.occurrence_date.between(start, end),
            ))
            .all())


def _log_registers():
    """Registers offered by "+ Log entry": all of them, for unplanned work."""
    # A one-register group shares the register's name, so it shows no group.
    out = []
    for reg in HSE_REGISTERS:
        group = GROUP_LABELS.get(reg.group, reg.group.title())
        out.append({'key': reg.key, 'label': reg.label,
                    'group': group if group != reg.label else ''})
    return out


def _drawer(grouped, day, today):
    """The drawer's view model, or None when no day is open."""
    if day is None:
        return None
    cards = drawer_cards(grouped.get(day, []), today)
    return {'date': day, 'cards': cards, 'summary': day_summary(cards)}


def _view_model(start, end, today, state):
    """Month view data. `grouped_all` is unfiltered so chip counts cover the
    whole window, not just the active chip's slice."""
    schedules = _schedules()
    entries = _entries(start, end)
    grouped_all = items_by_day(schedules, entries, start, end, today)
    grouped = (items_by_day(schedules, entries, start, end, today, state)
               if state else grouped_all)
    return schedules, entries, grouped_all, grouped


@hse_bp.route('/calendar')
@login_required
@require('view_hse')
def calendar_month():
    today = date.today()
    state = request.args.get('state') or None

    if request.args.get('view') == 'agenda':
        return _agenda(today, state)

    year, month = parse_month(request.args.get('month'), today)
    start, end = grid_bounds(year, month)
    schedules, entries, grouped_all, grouped = _view_model(start, end, today, state)

    weeks = month_grid(grouped, year, month, today)
    month_start = date(year, month, 1)
    month_end = date(*shift_month(year, month, 1), 1) - timedelta(days=1)

    selected = parse_day(request.args.get('day')) or default_day(weeks, today)
    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)

    return render_template(
        'hse/calendar.html',
        active_view='month',
        weeks=weeks,
        kpis=kpis(schedules, entries, month_start, month_end, today),
        chips=state_chips(grouped_all, state),
        active_state=state,
        today=today,
        month_label=month_start.strftime('%B %Y'),
        prev_month='%04d-%02d' % (prev_y, prev_m),
        next_month='%04d-%02d' % (next_y, next_m),
        this_month='%04d-%02d' % (today.year, today.month),
        selected_day=selected,
        drawer=_drawer(grouped, selected, today),
        log_registers=_log_registers(),
        month_chip=month_start.strftime('%b %Y'),
        rail=rail_items(open_counts_by_register(today), active_group='calendar'),
        active_group='calendar',
        active_sub='calendar',
    )


def _agenda(today, state):
    start = today
    end = today + timedelta(days=AGENDA_DAYS)
    # Header KPIs cover this month, matching the Month view.
    month_start = date(today.year, today.month, 1)
    month_end = date(*shift_month(today.year, today.month, 1), 1) - timedelta(days=1)

    schedules = _schedules()
    entries = _entries(min(start, month_start), max(end, month_end))
    grouped_all = items_by_day(schedules, entries, start, end, today)
    grouped = (items_by_day(schedules, entries, start, end, today, state)
               if state else grouped_all)

    return render_template(
        'hse/calendar_agenda.html',
        active_view='agenda',
        groups=agenda_groups(grouped, today),
        log_registers=_log_registers(),
        kpis=kpis(schedules, entries, month_start, month_end, today),
        chips=state_chips(grouped_all, state),
        active_state=state,
        today=today,
        days_ahead=AGENDA_DAYS,
        rail=rail_items(open_counts_by_register(today), active_group='calendar'),
        active_group='calendar',
        active_sub='calendar',
    )


@hse_bp.route('/calendar/day/<datestr>')
@login_required
@require('view_hse')
def calendar_day(datestr):
    """The drawer for one day, fetched when a day cell is clicked."""
    target = parse_day(datestr)
    if target is None:
        abort(404)
    today = date.today()
    state = request.args.get('state') or None

    schedules = _schedules()
    entries = _entries(target, target)
    grouped = items_by_day(schedules, entries, target, target, today, state)

    return render_template(
        'hse/_calendar_drawer.html',
        drawer=_drawer(grouped, target, today),
        today=today,
    )


@hse_bp.route('/calendar/today')
@login_required
@require('view_hse')
def calendar_today():
    """Bookmarkable Today link: redirects to the current month with today open."""
    today = date.today()
    return redirect(url_for('hse.calendar_month',
                            month='%04d-%02d' % (today.year, today.month),
                            day=today.isoformat()))
