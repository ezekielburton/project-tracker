import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import User, NotificationSound
from app.modules.core.shared.lib.decorators import role_required
from app.modules.core.shared.services.achievements import check_achievements


auth = Blueprint('auth', __name__, template_folder='../templates')


# Profile view/edit routes and the profile-image helpers live in the profile
# module, not here — this blueprint covers auth and account settings only.


@auth.route('/register', methods=['GET', 'POST'])
@login_required
@role_required('admin')
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

        # Team is required only for designer and team_lead roles
        if role in ['designer', 'team_lead'] and not team:
            errors.append('Team must be selected for Designer and Team Lead roles.')

        # For roles that don't have a team, clear the team field
        if role not in ['designer', 'team_lead']:
            team = None

        # Check email uniqueness
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
            # Preserve next so the redirect still works after a failed attempt
            return redirect(url_for('auth.login', next=request.form.get('next', '')))

        if not user.is_active:
            flash('This account has been deactivated. Contact an admin if this is a mistake.', 'error')
            return redirect(url_for('auth.login', next=request.form.get('next', '')))

        login_user(user, remember=True)
        check_achievements(user, 'user_login')
        flash(f'Welcome back, {user.name}.', 'success')
        next_page = request.form.get('next') or ''
        # Flask-Login sometimes sets next to a full URL — extract just the path
        if next_page and not next_page.startswith('/'):
            from urllib.parse import urlparse
            parsed = urlparse(next_page)
            next_page = parsed.path + ('?' + parsed.query if parsed.query else '')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)

        # Land on the role-based dashboard after login. Its endpoint is
        # projects.index (the dashboard blueprint; see main.index in the app
        # factory for the endpoint-naming note). dashboard.py's index()
        # selects the right role template (dashboard_cs/_leadership/_designer)
        # internally via layout_role, so no per-role deep link is needed here.
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

   # Parse current notification prefs to pass to the template (default empty dict = all on)
    try:
        current_prefs = json.loads(current_user.notification_prefs or '{}')
    except (ValueError, TypeError):
        current_prefs = {}

    available_sounds = NotificationSound.query.order_by(NotificationSound.name).all()

    # Imported inline (used only in this route). Achievement-domain logic
    # lives in the profile module; this pulls the Active Rewards + pinning
    # data shown in the account page's rewards sections.
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

    # Whitelist of valid pref keys — ignore anything unknown
    valid_keys = {
        'new_project', 'lead_assigned', 'concept_kv_assigned', 'revision_flag',
        'flag_reply', 'flag_resolved', 'brief_flag', 'revision_submitted',
        'project_started', 'lead_changed', 'deliverable_status',
        'project_submitted_client', 'project_approved', 'email_decision_flag'
    }
    # Build a clean dict of only known keys with boolean values
    prefs = {k: bool(v) for k, v in data.items() if k in valid_keys}
    current_user.notification_prefs = json.dumps(prefs)
    db.session.commit()
    return jsonify({'success': True})


@auth.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    users = User.query.order_by(User.name).all()
    # dev_tools_enabled is injected globally via context processor in app/__init__.py
    return render_template('auth/users.html', users=users)


@auth.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@role_required('admin')
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    user.set_password('Vitamin2026!')
    db.session.commit()
    flash(f'Password for {user.name} has been reset to Vitamin2026!', 'success')
    return redirect(url_for('auth.admin_users'))

@auth.route('/account/sound-prefs', methods=['POST'])
@login_required
def save_sound_prefs():
    """
    Save the user's sound-related preferences (on/off, chosen sound, volume)
    into the same notification_prefs JSON blob used for email prefs.
    Kept as its own route rather than folded into save_notification_prefs,
    because that route force-casts every value to bool — fine for on/off
    toggles, but it would corrupt a volume float or a sound_id.
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Read-modify-write: load whatever's already there so we don't clobber
    # the unrelated email-toggle keys living in this same JSON column.
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
            pass  # ignore a malformed value rather than 500ing the request

    if 'sound_id' in data:
        sound_id = data['sound_id']
        # Accept null (reset to default chime) or a real, still-existing sound
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