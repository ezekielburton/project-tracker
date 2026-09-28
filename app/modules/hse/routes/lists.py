"""
HSE Lists: reference lists, people and assets, managed by the officer
(manage_hse) so no admin is needed to add a value.

Nothing is deleted. Filed entries still point at values, so a retired one
is deactivated and drops out of dropdowns.
"""
from flask import abort, jsonify, render_template, request, url_for
from flask_login import login_required

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import require, require_api
from app.modules.hse.lib.flags import rail_counts
from app.modules.hse.lib.lists import (
    KIND_LABELS, find_or_revive_reference, kind_label, panel_for,
    serialize_asset, serialize_person, serialize_reference, tabs,
)
from app.modules.hse.lib.rail import rail_items
from app.modules.hse.models import (
    ASSET_KINDS, REFERENCE_KINDS, HseAsset, HsePerson, HseReference,
)
from app.modules.hse.routes.blueprint import hse_bp


MAX_LABEL = 160
MAX_SERIAL = 120


def _clean(value, field='label'):
    """A trimmed, non-empty, bounded label — or an error message."""
    text = (value or '').strip()
    if not text:
        return None, f'{field.capitalize()} is required'
    if len(text) > MAX_LABEL:
        return None, f'{field.capitalize()} is too long'
    return text, None


def _serial(value):
    """A trimmed serial number or None — or an error message."""
    text = (value or '').strip()
    if len(text) > MAX_SERIAL:
        return None, 'Serial no. is too long'
    return text or None, None


@hse_bp.route('/lists')
@hse_bp.route('/lists/<tab_key>')
@login_required
@require('manage_hse')
def lists_page(tab_key=None):
    available = tabs()
    keys = [t['key'] for t in available]
    if tab_key is None:
        tab_key = keys[0]
    if tab_key not in keys:
        abort(404)
    return render_template(
        'hse/lists.html',
        sections=panel_for(tab_key),
        rail=rail_items(rail_counts()),
        active_group='lists',
        active_sub=tab_key,
        list_pages=[{'key': t['key'], 'label': t['label'],
                     'url': url_for('hse.lists_page', tab_key=t['key'])}
                    for t in available],
    )


# ── Reference lists ────────────────────────────────────────────────

@hse_bp.route('/lists/reference', methods=['POST'])
@login_required
@require_api('manage_hse')
def create_reference():
    data = request.get_json(silent=True) or {}
    kind = data.get('kind')
    if kind not in REFERENCE_KINDS:
        return jsonify({'error': 'Unknown list'}), 400
    label, error = _clean(data.get('label'))
    if error:
        return jsonify({'error': error}), 400

    row, created = find_or_revive_reference(kind, label)
    if created and row.id is None:
        db.session.add(row)
    db.session.commit()
    return jsonify({'row': serialize_reference(row)}), 201 if created else 200


@hse_bp.route('/lists/reference/<int:row_id>', methods=['PATCH'])
@login_required
@require_api('manage_hse')
def update_reference(row_id):
    row = HseReference.query.get_or_404(row_id)
    data = request.get_json(silent=True) or {}

    if 'label' in data:
        label, error = _clean(data.get('label'))
        if error:
            return jsonify({'error': error}), 400
        clash = (HseReference.query
                 .filter(HseReference.kind == row.kind, HseReference.label == label,
                         HseReference.id != row.id).first())
        if clash:
            return jsonify({'error': f'"{label}" is already in {kind_label(row.kind)}'}), 409
        row.label = label

    if 'active' in data:
        row.active = bool(data.get('active'))

    db.session.commit()
    return jsonify({'row': serialize_reference(row)})


# ── People ─────────────────────────────────────────────────────────

@hse_bp.route('/lists/people', methods=['POST'])
@login_required
@require_api('manage_hse')
def create_person():
    data = request.get_json(silent=True) or {}
    name, error = _clean(data.get('name'), 'name')
    if error:
        return jsonify({'error': error}), 400

    person = HsePerson(
        name=name,
        role=(data.get('role') or '').strip() or None,
        organisation=(data.get('organisation') or '').strip() or None,
        is_external=bool(data.get('is_external')),
        can_hold_actions=bool(data.get('can_hold_actions')),
        email=(data.get('email') or '').strip() or None,
        phone=(data.get('phone') or '').strip() or None,
    )
    db.session.add(person)
    db.session.commit()
    return jsonify({'row': serialize_person(person)}), 201


@hse_bp.route('/lists/people/<int:person_id>', methods=['PATCH'])
@login_required
@require_api('manage_hse')
def update_person(person_id):
    person = HsePerson.query.get_or_404(person_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name, error = _clean(data.get('name'), 'name')
        if error:
            return jsonify({'error': error}), 400
        person.name = name
    for field in ('role', 'organisation', 'email', 'phone'):
        if field in data:
            setattr(person, field, (data.get(field) or '').strip() or None)
    for flag in ('is_external', 'can_hold_actions', 'active'):
        if flag in data:
            setattr(person, flag, bool(data.get(flag)))

    db.session.commit()
    return jsonify({'row': serialize_person(person)})


# ── Assets ─────────────────────────────────────────────────────────

@hse_bp.route('/lists/assets', methods=['POST'])
@login_required
@require_api('manage_hse')
def create_asset():
    data = request.get_json(silent=True) or {}
    if data.get('kind') not in ASSET_KINDS:
        return jsonify({'error': 'Unknown asset kind'}), 400
    label, error = _clean(data.get('label'))
    if error:
        return jsonify({'error': error}), 400
    serial_no, error = _serial(data.get('serial_no'))
    if error:
        return jsonify({'error': error}), 400

    asset = HseAsset(kind=data['kind'], label=label,
                     ref=(data.get('ref') or '').strip() or None,
                     serial_no=serial_no)
    db.session.add(asset)
    db.session.commit()
    return jsonify({'row': serialize_asset(asset)}), 201


@hse_bp.route('/lists/assets/<int:asset_id>', methods=['PATCH'])
@login_required
@require_api('manage_hse')
def update_asset(asset_id):
    asset = HseAsset.query.get_or_404(asset_id)
    data = request.get_json(silent=True) or {}

    if 'label' in data:
        label, error = _clean(data.get('label'))
        if error:
            return jsonify({'error': error}), 400
        asset.label = label
    if 'ref' in data:
        asset.ref = (data.get('ref') or '').strip() or None
    if 'serial_no' in data:
        serial_no, error = _serial(data.get('serial_no'))
        if error:
            return jsonify({'error': error}), 400
        asset.serial_no = serial_no
    if 'active' in data:
        asset.active = bool(data.get('active'))

    db.session.commit()
    return jsonify({'row': serialize_asset(asset)})


# ── Quick-add, from inside the entry form ──────────────────────────

@hse_bp.route('/lists/reference/quick-add', methods=['POST'])
@login_required
@require_api('manage_hse')
def quick_add_reference():
    """Adds a missing list value from inside the entry form, so the user
    never has to leave a half-filled entry."""
    data = request.get_json(silent=True) or {}
    kind = data.get('kind')
    if kind not in REFERENCE_KINDS:
        return jsonify({'error': 'Unknown list'}), 400
    label, error = _clean(data.get('label'))
    if error:
        return jsonify({'error': error}), 400

    row, _ = find_or_revive_reference(kind, label)
    if row.id is None:
        db.session.add(row)
    db.session.commit()
    return jsonify({'row': serialize_reference(row)}), 201
