"""
HSE — creating and editing an entry.

The overlay is fetched rather than baked into the page, so its dropdowns
always reflect the reference lists as they are now instead of whatever they
held when the table was rendered.
"""
from datetime import date

from flask import abort, jsonify, render_template, request
from flask_login import login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import effective_user, require, require_api
from app.modules.core.shared.lib.utils import log_activity
from app.modules.hse.lib.forms import (
    LOCKED_FIELDS, ValidationError, apply_payload, blocking_empty_lists, form_fields,
)
from app.modules.hse.lib.refs import next_ref
from app.modules.hse.lib.registers import register
from app.modules.hse.lib.schedule import falls_due_on
from app.modules.hse.models import HseEntry, HseSchedule
from app.modules.hse.routes.blueprint import hse_bp


def _register_or_404(register_key):
    reg = register(register_key)
    if reg is None:
        abort(404)
    return reg


def _parse_date(raw):
    try:
        return date.fromisoformat((raw or '').strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _prefill(reg, args):
    """Values the calendar already knows when it opens this form — the day
    clicked, and the asset the occurrence covers. Keyed by field name,
    resolved through the declaration rather than hard-coded, so a register
    that names its date field differently still fills in."""
    out = {}
    day = args.get('date')
    asset = args.get('asset')
    for field in reg.fields:
        if day and field.column == 'entry_date':
            out[field.name] = day
        if asset and asset.isdigit() and field.type == 'asset':
            out[field.name] = int(asset)
    return out


def _occurrence(reg, schedule_id, occurrence_date):
    """Validate a claimed occurrence, or explain why it is not one.

    Returns (context, error). The context is what gets stamped onto the
    entry; `error` is a message for the form.

    This check is the reason coverage can be trusted: without it any
    request could name a schedule and a date and tick off work that was
    never planned.
    """
    if not schedule_id and not occurrence_date:
        return None, None
    if not schedule_id or not occurrence_date:
        return None, 'An occurrence needs both a schedule and a date.'

    day = _parse_date(occurrence_date) if isinstance(occurrence_date, str) else occurrence_date
    if day is None:
        return None, 'That occurrence date is not a date.'

    schedule = HseSchedule.query.get(schedule_id)
    if schedule is None or not schedule.active:
        return None, 'That schedule no longer exists.'
    if schedule.register != reg.key:
        return None, f'That schedule does not belong to the {reg.label} register.'
    if not falls_due_on(schedule, day):
        return None, 'Nothing was scheduled on that date.'

    return {'schedule_id': schedule.id, 'date': day}, None


@hse_bp.route('/<register_key>/form')
@login_required
@require('manage_hse')
def new_entry_form(register_key):
    """The empty overlay for a register — or, when the calendar opened it,
    one already carrying the day, the asset and the occurrence it will
    tick off."""
    reg = _register_or_404(register_key)
    occurrence, _error = _occurrence(
        reg, request.args.get('schedule'), request.args.get('occurrence'))
    return render_template(
        'hse/_entry_modal.html',
        reg=reg, entry=None,
        fields=form_fields(reg, prefill=_prefill(reg, request.args)),
        locked=LOCKED_FIELDS,
        blocked_by=blocking_empty_lists(reg),
        occurrence=occurrence,
        today=date.today().isoformat(),
    )


@hse_bp.route('/entry/<int:entry_id>/form')
@login_required
@require('manage_hse')
def edit_entry_form(entry_id):
    """The same overlay, filled in."""
    entry = HseEntry.query.get_or_404(entry_id)
    reg = _register_or_404(entry.register)
    return render_template(
        'hse/_entry_modal.html',
        reg=reg, entry=entry,
        fields=form_fields(reg, entry),
        locked=LOCKED_FIELDS,
        blocked_by=blocking_empty_lists(reg),
        occurrence=None,
        today=date.today().isoformat(),
    )


@hse_bp.route('/<register_key>/entries', methods=['POST'])
@login_required
@require_api('manage_hse')
def create_entry(register_key):
    reg = _register_or_404(register_key)
    blocked = blocking_empty_lists(reg)
    if blocked:
        return jsonify({'error': f'Set up {", ".join(blocked)} before filing an entry.'}), 400

    actor = effective_user()
    payload = request.get_json(silent=True) or {}

    occurrence, error = _occurrence(
        reg, payload.get('schedule_id'), payload.get('occurrence_date'))
    if error:
        return jsonify({'error': error}), 400

    entry = HseEntry(register=reg.key, created_by_id=actor.id)
    try:
        apply_payload(entry, reg, payload)
    except ValidationError as e:
        return jsonify({'errors': e.errors}), 400

    if occurrence:
        entry.schedule_id = occurrence['schedule_id']
        entry.occurrence_date = occurrence['date']

    # Allocated last, so a rejected form never burns a reference number.
    entry.ref = next_ref(reg.key)
    db.session.add(entry)
    db.session.commit()

    log_activity('hse_entry_created', f'{actor.name} filed {entry.ref} in {reg.label}',
                 user=actor, entity_type='hse_entry', entity_name=entry.ref, entity_id=entry.id)
    return jsonify({'id': entry.id, 'ref': entry.ref}), 201


@hse_bp.route('/entry/<int:entry_id>', methods=['PATCH'])
@login_required
@require_api('manage_hse')
def update_entry(entry_id):
    entry = HseEntry.query.get_or_404(entry_id)
    reg = _register_or_404(entry.register)
    actor = effective_user()

    try:
        apply_payload(entry, reg, request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({'errors': e.errors}), 400

    db.session.commit()
    log_activity('hse_entry_updated', f'{actor.name} updated {entry.ref}',
                 user=actor, entity_type='hse_entry', entity_name=entry.ref, entity_id=entry.id)
    return jsonify({'id': entry.id, 'ref': entry.ref})
