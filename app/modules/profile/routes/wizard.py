from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from datetime import date

wizard_bp = Blueprint('wizard', __name__)


@wizard_bp.route('/wizard/complete', methods=['POST'])
@login_required
def complete():
    from app.modules.core.shared.extensions import db
    import json

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Step 1 — display name; blank leaves it unchanged.
    name = (data.get('name') or '').strip()
    if name:
        current_user.name = name

    # Step 1 — optional password. Same 8-char minimum as auth's /account route.
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
            pass  # ignore a malformed date

    favorite_food = (data.get('favorite_food') or '').strip()
    if favorite_food:
        current_user.favorite_food = favorite_food

    # Step 3 — notification preferences. Read-modify-write: the
    # notification_prefs blob is shared with auth's pref routes.
    try:
        prefs = json.loads(current_user.notification_prefs or '{}')
    except (ValueError, TypeError):
        prefs = {}

    # Must match valid_keys in auth's save_notification_prefs.
    EMAIL_PREF_KEYS = {
        'concept_kv_assigned', 'preprod_stream_approved', 'brief_flag',
        'preprod_stream_uploaded', 'due_date_changed', 'job_number_changed',
        'client_spoc_changed', 'flag_reply', 'flag_resolved', 'lead_changed',
        'project_submitted_client', 'project_approved',
    }
    # Sent only when the email step was shown (not in the avatar-only
    # wizard), so saved opt-outs are never cleared by a step the user skipped.
    if 'email_enabled' in data:
        if data['email_enabled']:
            # An absent key means enabled, so clear any saved False.
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