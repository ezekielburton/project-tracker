from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from datetime import date

wizard_bp = Blueprint('wizard', __name__)


@wizard_bp.route('/wizard/complete', methods=['POST'])
@login_required
def complete():
    from app import db
    import json

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Step 1 — display name. No-op if the field was never shown/edited.
    name = (data.get('name') or '').strip()
    if name:
        current_user.name = name

    # Step 1 — password (optional). Same 8-char minimum as auth.py's
    # /account route, checked again here even though wizard.js already
    # checks it client-side — never trust client-side validation alone.
    password = data.get('password') or ''
    password_confirm = data.get('password_confirm') or ''
    if password:
        if password != password_confirm:
            return jsonify({'success': False, 'error': 'Passwords do not match.'}), 400
        if len(password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters.'}), 400
        current_user.set_password(password)

    # Step 2 — birthday + favourite food, both optional.
    birthday = data.get('birthday')
    if birthday:
        try:
            current_user.birthday = date.fromisoformat(birthday)
        except ValueError:
            pass  # malformed date — ignore rather than 500 the whole request

    favorite_food = (data.get('favorite_food') or '').strip()
    if favorite_food:
        current_user.favorite_food = favorite_food

    # Step 3 — notification preferences. Same read-modify-write pattern as
    # auth.py's save_notification_prefs / save_sound_prefs — all three
    # routes share the one notification_prefs JSON blob on User.
    try:
        prefs = json.loads(current_user.notification_prefs or '{}')
    except (ValueError, TypeError):
        prefs = {}

    # Mirrors the valid_keys whitelist in auth.py's save_notification_prefs.
    # Keep these two lists in sync if a new per-event pref key is ever added.
    EMAIL_PREF_KEYS = {
        'new_project', 'lead_assigned', 'concept_kv_assigned', 'revision_flag',
        'flag_reply', 'flag_resolved', 'brief_flag', 'revision_submitted',
        'project_started', 'lead_changed', 'deliverable_status',
        'project_submitted_client', 'project_approved'
    }
    if data.get('email_enabled', True):
        # "On" is the default — absent key already means enabled, so just
        # clear out any explicit False a previous save might have left.
        for key in EMAIL_PREF_KEYS:
            prefs.pop(key, None)
    else:
        for key in EMAIL_PREF_KEYS:
            prefs[key] = False

    if 'sound_enabled' in data:
        prefs['sound_enabled'] = bool(data['sound_enabled'])
    if 'sound_volume' in data:
        try:
            prefs['sound_volume'] = max(0.0, min(1.0, float(data['sound_volume'])))
        except (TypeError, ValueError):
            pass

    current_user.notification_prefs = json.dumps(prefs)
    current_user.wizard_completed = True
    current_user.avatar_step_completed = True
    db.session.commit()

    return jsonify({'success': True})