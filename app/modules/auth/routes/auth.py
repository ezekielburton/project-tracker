import json
import secrets
import string
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import User, NotificationSound
from app.modules.core.shared.lib.capabilities import require
from app.modules.core.shared.services.achievements import check_achievements


auth = Blueprint('auth', __name__, template_folder='../templates')


# Auth and account settings only; profile pages live in the profile module.


def _safe_next_path(target):
    """Return `target` if it is a same-site relative path, else None.
    Browsers read a backslash as a slash, so '/\\evil.com' is '//evil.com';
    they also drop tabs/newlines, so control characters are refused too."""
    if not target or not target.startswith('/'):
        return None
    if target.replace('\\', '/').startswith('//'):
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in target):
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def generate_temp_password():
    """Random one-off password for an admin reset; shown once to that admin."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(12))


@auth.route('/register', methods=['GET', 'POST'])
@login_required
@require('manage_users', real_user=True)
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        role = request.form.get('role')
        team = request.form.get('team')

        errors = []

        if not name:
            errors.append('Full name is required.')
        if not email:
            errors.append('Email is required.')
        if not password:
            errors.append('Password is required.')
        if not role:
            errors.append('Role is required.')

        if role in ['designer', 'team_lead'] and not team:
            errors.append('Team must be selected for Designer and Team Lead roles.')

        if role not in ['designer', 'team_lead']:
            team = None

        if email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                errors.append('An account with that email already exists.')

        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('auth.register'))

        hashed_password = generate_password_hash(password)

        new_user = User(
            name=name,
            email=email,
            password_hash=hashed_password,
            role=role,
            team=team
        )

        db.session.add(new_user)
        db.session.commit()

        flash(f'Account created successfully for {name}.', 'success')
        return redirect(url_for('auth.register'))

    return render_template('auth/register.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')

        user = User.query.filter(User.email.ilike(email)).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash('Incorrect email or password.', 'error')
            # Keep next so a retry still lands on the page asked for.
            return redirect(url_for('auth.login', next=request.form.get('next', '')))

        if not user.is_active:
            flash('This account has been deactivated. Contact an admin if this is a mistake.', 'error')
            return redirect(url_for('auth.login', next=request.form.get('next', '')))

        login_user(user, remember=True)
        check_achievements(user, 'user_login')
        flash(f'Welcome back, {user.name}.', 'success')
        next_page = _safe_next_path(request.form.get('next'))
        if next_page:
            return redirect(next_page)

        # projects.index is the role-based dashboard (dashboard.py's blueprint
        # is named 'projects'); it picks the layout by role.
        return redirect(url_for('projects.index'))

    return render_template('auth/login.html', next=request.args.get('next', ''))


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('auth.account'))

        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('auth.account'))

        if len(new_password) < 8:
            flash('New password must be at least 8 characters.', 'error')
            return redirect(url_for('auth.account'))

        current_user.set_password(new_password)
        db.session.commit()
        flash('Password updated successfully.', 'success')
        return redirect(url_for('auth.account'))

    # Missing keys mean "on", so an empty dict is all toggles on.
    try:
        current_prefs = json.loads(current_user.notification_prefs or '{}')
    except (ValueError, TypeError):
        current_prefs = {}

    available_sounds = NotificationSound.query.order_by(NotificationSound.name).all()

    # Achievement data for the account page's rewards sections (profile module).
    from app.modules.profile.routes.profile import _build_account_achievement_context
    achievement_context = _build_account_achievement_context(current_user)

    return render_template(
        'auth/account.html',
        notification_prefs=current_prefs,
        available_sounds=available_sounds,
        **achievement_context
    )

@auth.route('/account/notification-prefs', methods=['POST'])
@login_required
def save_notification_prefs():
    """Save the user's email notification preferences as a JSON blob."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Every toggle account.html renders; unknown keys are ignored.
    valid_keys = {
        'concept_kv_assigned', 'preprod_stream_approved', 'brief_flag',
        'preprod_stream_uploaded', 'due_date_changed', 'job_number_changed',
        'client_spoc_changed', 'flag_reply', 'flag_resolved', 'lead_changed',
        'project_submitted_client', 'project_approved',
    }
    # Read-modify-write: the blob also holds sound prefs and the toggles of
    # other roles, which this page doesn't send.
    try:
        prefs = json.loads(current_user.notification_prefs or '{}')
    except (ValueError, TypeError):
        prefs = {}
    prefs.update({k: bool(v) for k, v in data.items() if k in valid_keys})
    current_user.notification_prefs = json.dumps(prefs)
    db.session.commit()
    return jsonify({'success': True})


@auth.route('/admin/users')
@login_required
@require('manage_users', real_user=True)
def admin_users():
    users = User.query.order_by(User.name).all()
    return render_template('auth/users.html', users=users)


@auth.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@require('manage_users', real_user=True)
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    temp_password = generate_temp_password()
    user.set_password(temp_password)
    db.session.commit()
    flash(f'Password for {user.name} has been reset to {temp_password} — '
          f'share it with them now; it will not be shown again.', 'success')
    return redirect(url_for('auth.admin_users'))

@auth.route('/account/sound-prefs', methods=['POST'])
@login_required
def save_sound_prefs():
    """Save sound prefs (on/off, sound, volume) into the notification_prefs
    blob. Separate from save_notification_prefs, which casts every value to bool."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Read-modify-write: the blob also holds the email toggles.
    try:
        prefs = json.loads(current_user.notification_prefs or '{}')
    except (ValueError, TypeError):
        prefs = {}

    if 'sound_enabled' in data:
        prefs['sound_enabled'] = bool(data['sound_enabled'])

    if 'sound_volume' in data:
        try:
            prefs['sound_volume'] = max(0.0, min(1.0, float(data['sound_volume'])))
        except (TypeError, ValueError):
            pass  # ignore a malformed value

    if 'sound_id' in data:
        sound_id = data['sound_id']
        # null resets to the default chime; otherwise the sound must exist.
        if sound_id is None or NotificationSound.query.get(sound_id):
            prefs['sound_id'] = sound_id

    current_user.notification_prefs = json.dumps(prefs)
    db.session.commit()
    return jsonify({'success': True})


@auth.route('/account/theme-prefs', methods=['POST'])
@login_required
def save_theme_prefs():
    """Save the user's light/dark theme choice, fire-and-forget from the toggle."""
    data = request.get_json(silent=True)
    if data is None or data.get('theme') not in ('light', 'dark'):
        return jsonify({'success': False, 'error': 'Invalid theme'}), 400

    current_user.theme_preference = data['theme']
    db.session.commit()
    return jsonify({'success': True})