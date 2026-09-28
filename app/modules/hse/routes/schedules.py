"""
HSE Schedule page (rail sub-page of Calendar): the recurring plan the
calendar is drawn from.

Viewing is view_hse so management can see the plan; editing is manage_hse.
(Lists, by contrast, are manage_hse to view.) Nothing here creates an
entry or stores an occurrence.
"""
from datetime import date, timedelta

from flask import jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import effective_user, require, require_api
from app.modules.core.shared.lib.utils import log_activity
from app.modules.hse.lib.query import open_counts_by_register
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.lib.schedules import (
    LOOKBACK_DAYS, ValidationError, apply_payload, clean_payload, display_row,
    form_options, form_payload, preview_dates, serialize_schedule,
)
from app.modules.hse.models import HseAsset, HseEntry, HsePerson, HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


def _schedules():
    return (HseSchedule.query
            .options(selectinload(HseSchedule.owner), selectinload(HseSchedule.assets))
            .order_by(HseSchedule.active.desc(), HseSchedule.label)
            .all())


def _active_assets():
    return (HseAsset.query.filter_by(active=True)
            .order_by(HseAsset.kind, HseAsset.label).all())


def _assets_by_id():
    return {a.id: a for a in _active_assets()}


def _scheduled_entries(today):
    """Entries filed against a schedule within the lookback window; the due
    column uses them to see which recent occurrences were done."""
    return (HseEntry.query
            .filter(HseEntry.schedule_id.isnot(None),
                    HseEntry.occurrence_date >= today - timedelta(days=LOOKBACK_DAYS),
                    HseEntry.occurrence_date <= today)
            .all())


def _last_done():
    """Latest occurrence date filed per schedule, in one aggregate query."""
    rows = (db.session.query(HseEntry.schedule_id,
                             func.max(HseEntry.occurrence_date))
            .filter(HseEntry.schedule_id.isnot(None))
            .group_by(HseEntry.schedule_id)
            .all())
    return {schedule_id: last for schedule_id, last in rows}


def _payload(schedule):
    """Save response: the table row plus the values that refill the form."""
    today = date.today()
    row = serialize_schedule(schedule, today,
                             _scheduled_entries(today), _last_done())
    return {'schedule': display_row(row), 'form': form_payload(row)}


@hse_bp.route('/calendar/schedule')
@login_required
@require('view_hse')
def schedule_page():
    today = date.today()
    people = HsePerson.query.filter_by(active=True).order_by(HsePerson.name).all()
    entries, last_done = _scheduled_entries(today), _last_done()
    rows = [serialize_schedule(s, today, entries, last_done) for s in _schedules()]
    live = [r for r in rows if r['active']]
    return render_template(
        'hse/schedule.html',
        rows=rows,
        count_live=len(live),
        count_overdue=sum(1 for r in live if r['due']['overdue_days']),
        forms={r['id']: form_payload(r) for r in rows},
        options=form_options(),
        people=[{'id': p.id, 'label': p.name} for p in people],
        assets=[{'id': a.id, 'label': a.label, 'kind': a.kind, 'ref': a.ref}
                for a in _active_assets()],
        rail=rail_items(open_counts_by_register(today), active_group='calendar'),
        active_group='calendar',
        active_sub='schedule',
    )


@hse_bp.route('/calendar/schedules', methods=['POST'])
@login_required
@require_api('manage_hse')
def create_schedule():
    actor = effective_user()
    schedule = HseSchedule(active=True)
    try:
        apply_payload(schedule, request.get_json(silent=True) or {}, _assets_by_id())
    except ValidationError as e:
        return jsonify({'errors': e.errors}), 400

    db.session.add(schedule)
    db.session.commit()
    log_activity('hse_schedule_created',
                 f'{actor.name} scheduled {schedule.label}',
                 user=actor, entity_type='hse_schedule',
                 entity_name=schedule.label, entity_id=schedule.id)
    return jsonify(_payload(schedule)), 201


@hse_bp.route('/calendar/schedules/<int:schedule_id>', methods=['PATCH'])
@login_required
@require_api('manage_hse')
def update_schedule(schedule_id):
    """Full edit, or retire/restore when the body is only `active`.
    Schedules are never deleted: entries and past occurrences reference them."""
    schedule = HseSchedule.query.get_or_404(schedule_id)
    actor = effective_user()
    payload = request.get_json(silent=True) or {}

    if set(payload) == {'active'}:
        schedule.active = bool(payload['active'])
        db.session.commit()
        log_activity('hse_schedule_updated',
                     f'{actor.name} {"restored" if schedule.active else "retired"} '
                     f'{schedule.label}',
                     user=actor, entity_type='hse_schedule',
                     entity_name=schedule.label, entity_id=schedule.id)
        return jsonify(_payload(schedule))

    try:
        apply_payload(schedule, payload, _assets_by_id())
    except ValidationError as e:
        return jsonify({'errors': e.errors}), 400

    db.session.commit()
    log_activity('hse_schedule_updated', f'{actor.name} updated {schedule.label}',
                 user=actor, entity_type='hse_schedule',
                 entity_name=schedule.label, entity_id=schedule.id)
    return jsonify(_payload(schedule))


@hse_bp.route('/calendar/schedules/preview', methods=['POST'])
@login_required
@require_api('manage_hse')
def preview_schedule():
    """Next few dates the current form would produce. Uses the save
    validation (minus asset checks) so previews match what a save accepts."""
    try:
        values, _ = clean_payload(request.get_json(silent=True) or {},
                                  check_assets=False)
    except ValidationError as e:
        return jsonify({'errors': e.errors}), 400

    return jsonify({'dates': [d.isoformat() for d in preview_dates(values)]})
