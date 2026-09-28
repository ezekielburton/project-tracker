"""Profile page (own and other users'), profile edits, and the achievement
display-settings / pin routes. Login and account settings live in auth."""
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import User
from app.modules.core.shared.lib.profilepic import (
    save_profile_pic, delete_profile_pic, AVATAR_FOLDER, BANNER_FOLDER,
)

profile_bp = Blueprint('profile', __name__, template_folder='../templates')


def _format_earned_date(earned_at):
    """Formats a naive-UTC earned_at as 'Earned 3 Jun 2026' in Dubai time.
    Fixed +4 offset because ZoneInfo needs tzdata on Windows; the day is
    built by hand because %-d is not portable."""
    if not earned_at:
        return None
    from datetime import timezone, timedelta
    dubai_tz = timezone(timedelta(hours=4))
    local = earned_at.replace(tzinfo=timezone.utc).astimezone(dubai_tz)
    return f'Earned {local.day} {local.strftime("%b")} {local.year}'


def _build_achievement_tile(achievement, user_achievement):
    """Tile dict for one earned achievement (Pinned and Recent tabs).
    Callers pass earned rows only, so there is no locked/hidden state."""
    return {
        'id': achievement.id,
        'name': achievement.name,
        'badge_image': achievement.badge_image,
        'badge_type': achievement.badge_type,
        'earned_display': _format_earned_date(user_achievement.earned_at),
    }


def _build_achievement_context(profile_user, is_own_profile):
    """Achievement values for the profile template. Always returns every
    key (empty lists when not applicable); visitors get pinned tiles and
    counts only."""
    from app.modules.core.shared.models import Achievement, AchievementCategory, UserAchievement, UserPinnedAchievement

    # ── Pinned tiles — shown on BOTH own and other-user profiles ───────────
    pinned_rows = (
        UserPinnedAchievement.query
        .filter_by(user_id=profile_user.id)
        .order_by(UserPinnedAchievement.pin_order)
        .all()
    )
    pinned_tiles = [
        _build_achievement_tile(pin.user_achievement.achievement, pin.user_achievement)
        for pin in pinned_rows
    ]

    # ── Unlock counts — shown on both own and other-user profiles ──────────
    earned_count = (
        UserAchievement.query
        .filter_by(user_id=profile_user.id)
        .filter(UserAchievement.earned_at.isnot(None))
        .count()
    )
    total_count = Achievement.query.count()

    context = {
        'pinned_tiles': pinned_tiles,
        'recent_tiles': [],
        'achievement_checklist': [],
        'achievement_earned_count': earned_count,
        'achievement_total_count': total_count,
    }

    if not is_own_profile:
        # Visitors see pinned tiles only; no fallback to recent achievements.
        return context

    # ── Recent tiles (own profile only) ─────────────────────────────────────
    recent_rows = (
        UserAchievement.query
        .filter(UserAchievement.user_id == profile_user.id, UserAchievement.earned_at.isnot(None))
        .order_by(UserAchievement.earned_at.desc())
        .limit(5)
        .all()
    )
    context['recent_tiles'] = [_build_achievement_tile(ua.achievement, ua) for ua in recent_rows]

    # ── Full checklist, grouped by category, with progress bars ────────────
    # One query up front to avoid N+1 in the loop below.
    progress_by_achievement_id = {
        ua.achievement_id: ua
        for ua in UserAchievement.query.filter_by(user_id=profile_user.id).all()
    }

    categories = AchievementCategory.query.order_by(AchievementCategory.display_order).all()
    checklist = []
    for category in categories:
        category_achievements = (
            Achievement.query
            .filter_by(category_id=category.id)
            .order_by(Achievement.display_order)
            .all()
        )
        if not category_achievements:
            continue
        rows = []
        for achievement in category_achievements:
            user_achievement = progress_by_achievement_id.get(achievement.id)
            progress = user_achievement.progress if user_achievement else 0
            earned_at = user_achievement.earned_at if user_achievement else None

            # Hidden and unearned: blank out name/badge so nothing leaks.
            # Once earned it shows like any other.
            locked = achievement.is_hidden and earned_at is None

            rows.append({
                'id': achievement.id,
                'name': None if locked else achievement.name,
                'badge_image': None if locked else achievement.badge_image,
                'badge_type': None if locked else achievement.badge_type,
                'locked': locked,
                'earned_display': _format_earned_date(earned_at),
                'progress': progress,
                'threshold': achievement.threshold,
                'percent': min(100, round(progress / achievement.threshold * 100)) if achievement.threshold else 0,
            })
        checklist.append({'category': category, 'achievements': rows})

    context['achievement_checklist'] = checklist
    return context


@profile_bp.route('/profile')
@profile_bp.route('/profile/<int:user_id>')
@login_required
def view(user_id=None):
    """Renders a profile: your own with no user_id, else that user's,
    view-only. Uses get_actor() so an emulating admin sees the emulated
    user's profile, without the edit controls."""
    from app.modules.core.shared.models import RoleTitle, DEFAULT_ROLE_TITLES, UserDisplaySettings, UserAchievement, AchievementBorder
    from app.modules.core.shared.lib.utils import get_actor

    actor = get_actor()
    profile_user = User.query.get_or_404(user_id) if user_id is not None else actor
    is_own_profile = actor.id == profile_user.id
    # Edit routes write to current_user (personal settings, like auth's
    # account page), so an emulating admin gets the emulated view, read-only.
    can_edit = is_own_profile and profile_user.id == current_user.id

    # Title, border and pins always come from the profile being viewed.
    role_title = RoleTitle.query.filter_by(role=profile_user.role).first()
    fun_title = role_title.title if role_title else DEFAULT_ROLE_TITLES.get(profile_user.role, '')

    # Active Rewards override the default title.
    active_border_class = None
    display_settings = UserDisplaySettings.query.filter_by(user_id=profile_user.id).first()
    if display_settings:
        if display_settings.active_title_id:
            active_title_ua = UserAchievement.query.get(display_settings.active_title_id)
            # The achievement may have lost its reward_title since it was chosen.
            if active_title_ua and active_title_ua.achievement.reward_title:
                fun_title = active_title_ua.achievement.reward_title

        if display_settings.active_border_id:
            border = AchievementBorder.query.get(display_settings.active_border_id)
            if border:
                active_border_class = border.css_class

    achievement_context = _build_achievement_context(profile_user, is_own_profile)

    # Badge picker + pin manager data, editable profile only.
    customize_context = {}
    if can_edit:
        customize_context = _build_account_achievement_context(profile_user)

    return render_template(
        'profile/profile.html',
        profile_user=profile_user,
        is_own_profile=is_own_profile,
        can_edit=can_edit,
        fun_title=fun_title,
        active_border_class=active_border_class,
        customize_context=customize_context,
        **achievement_context
    )


@profile_bp.route('/profile/avatar', methods=['POST'])
@login_required
def upload_avatar():
    """Saves current_user's avatar. This and the edit routes below always
    write to current_user, which is the security boundary; hiding the
    controls on other profiles is only UI."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    stored_filename = save_profile_pic(request.files['file'], AVATAR_FOLDER)
    if not stored_filename:
        return jsonify({'success': False, 'error': 'Invalid file'}), 400

    # Remove the old file so they don't pile up.
    delete_profile_pic(AVATAR_FOLDER, current_user.avatar_filename)

    current_user.avatar_filename = stored_filename
    db.session.commit()
    return jsonify({'success': True, 'url': url_for('static', filename=f'avatars/{stored_filename}')})


@profile_bp.route('/profile/banner', methods=['POST'])
@login_required
def upload_banner():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    stored_filename = save_profile_pic(request.files['file'], BANNER_FOLDER)
    if not stored_filename:
        return jsonify({'success': False, 'error': 'Invalid file'}), 400

    delete_profile_pic(BANNER_FOLDER, current_user.banner_filename)

    current_user.banner_filename = stored_filename
    db.session.commit()
    return jsonify({'success': True, 'url': url_for('static', filename=f'banners/{stored_filename}')})


@profile_bp.route('/profile/details', methods=['POST'])
@login_required
def update_profile_details():
    """Saves name, favorite_food and birthday from the Edit Details popup.
    Never reads role or fun_title, so a user cannot change their own role."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400
    current_user.name = name

    # None when blank, so the template hides the pill.
    current_user.favorite_food = (data.get('favorite_food') or '').strip() or None

    # <input type="date"> value 'yyyy-mm-dd'; empty clears the birthday.
    birthday_str = data.get('birthday')
    if birthday_str:
        try:
            current_user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid birthday format'}), 400
    else:
        current_user.birthday = None

    db.session.commit()
    return jsonify({'success': True})


@profile_bp.route('/profile/bio', methods=['POST'])
@login_required
def update_profile_bio():
    """Saves the bio from the Bio card's inline editor."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    bio = (data.get('bio') or '').strip()

    # Server-side backstop for the textarea's maxlength="1000".
    if len(bio) > 1000:
        return jsonify({'success': False, 'error': 'Bio must be 1000 characters or fewer'}), 400

    current_user.bio = bio or None
    db.session.commit()
    return jsonify({'success': True})

def _build_account_achievement_context(user):
    """Data for the Active Rewards pickers and the pin manager: earned
    achievements, title/border choices, current settings and pins in order.
    Also imported by auth's account view."""
    from app.modules.core.shared.models import UserAchievement, UserDisplaySettings, UserPinnedAchievement, AchievementBorder

    # Newest first; every choice below is filtered from this list.
    earned = (
        UserAchievement.query
        .filter(UserAchievement.user_id == user.id, UserAchievement.earned_at.isnot(None))
        .order_by(UserAchievement.earned_at.desc())
        .all()
    )

    title_choices = [ua for ua in earned if ua.achievement.reward_title]

    # Keyed by id to de-duplicate borders shared by several achievements.
    border_choices = {}
    for ua in earned:
        if ua.achievement.border_id:
            border = AchievementBorder.query.get(ua.achievement.border_id)
            if border:
                border_choices[border.id] = border

    # None for a user who has never saved settings.
    display_settings = UserDisplaySettings.query.filter_by(user_id=user.id).first()

    # Ids let the template exclude pinned items from the earned list; the
    # ordered list keeps pin_order.
    pinned_rows = (
        UserPinnedAchievement.query
        .filter_by(user_id=user.id)
        .order_by(UserPinnedAchievement.pin_order)
        .all()
    )
    pinned_ids = [p.user_achievement_id for p in pinned_rows]
    pinned_achievements_ordered = [p.user_achievement for p in pinned_rows]

    return {
        'earned_achievements': earned,
        'title_choices': title_choices,
        'border_choices': list(border_choices.values()),
        'display_settings': display_settings,
        'pinned_achievement_ids': pinned_ids,
        'pinned_achievements_ordered': pinned_achievements_ordered,
    }


@profile_bp.route('/account/display-settings', methods=['POST'])
@login_required
def save_display_settings():
    """Upserts the badge / title / border selections. Each id is optional
    (null clears it); all are validated before anything is written."""
    from app.modules.core.shared.models import UserDisplaySettings, UserAchievement, AchievementBorder

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    def _validated_user_achievement_id(key, require_reward_title=False):
        """Returns (True, id) if data[key] is null or an earned
        UserAchievement of this user, else (False, error message)."""
        if key not in data or data[key] is None:
            return True, None

        ua = UserAchievement.query.get(data[key])
        if not ua or ua.user_id != user_id or ua.earned_at is None:
            return False, f'Invalid or unearned achievement for {key}'
        if require_reward_title and not ua.achievement.reward_title:
            return False, f'{key} has no reward title to display'
        return True, data[key]

    user_id = current_user.id

    ok, badge_id_or_error = _validated_user_achievement_id('active_badge_id')
    if not ok:
        return jsonify({'success': False, 'error': badge_id_or_error}), 400

    ok, title_id_or_error = _validated_user_achievement_id('active_title_id', require_reward_title=True)
    if not ok:
        return jsonify({'success': False, 'error': title_id_or_error}), 400

    # A border id is an AchievementBorder id; it counts as earned when any
    # earned achievement references it.
    border_id = data.get('active_border_id')
    if border_id is not None:
        border = AchievementBorder.query.get(border_id)
        earned_border_ids = {
            ua.achievement.border_id for ua in
            UserAchievement.query.filter(
                UserAchievement.user_id == user_id, UserAchievement.earned_at.isnot(None)
            ).all()
            if ua.achievement.border_id
        }
        if not border or border.id not in earned_border_ids:
            return jsonify({'success': False, 'error': 'Invalid or unearned border'}), 400

    # One row per user (user_id is unique).
    settings = UserDisplaySettings.query.filter_by(user_id=user_id).first()
    if settings is None:
        settings = UserDisplaySettings(user_id=user_id)
        db.session.add(settings)

    settings.active_badge_id = badge_id_or_error
    settings.active_title_id = title_id_or_error
    settings.active_border_id = border_id

    db.session.commit()
    return jsonify({'success': True})


@profile_bp.route('/account/pinned-achievements', methods=['POST'])
@login_required
def save_pinned_achievements():
    """Replaces the user's pins with an ordered list of up to 5
    user_achievement_ids. Delete-and-recreate is safe: pins hold only order."""
    from app.modules.core.shared.models import UserAchievement, UserPinnedAchievement

    data = request.get_json(silent=True)
    if data is None or 'pinned_ids' not in data:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    pinned_ids = data['pinned_ids']

    if not isinstance(pinned_ids, list) or len(pinned_ids) > 5:
        return jsonify({'success': False, 'error': 'Must be a list of at most 5 achievements'}), 400

    if len(pinned_ids) != len(set(pinned_ids)):
        return jsonify({'success': False, 'error': 'Duplicate achievement in pin list'}), 400

    # Any bad id rejects the whole request.
    for ua_id in pinned_ids:
        ua = UserAchievement.query.get(ua_id)
        if not ua or ua.user_id != current_user.id or ua.earned_at is None:
            return jsonify({'success': False, 'error': f'Invalid or unearned achievement: {ua_id}'}), 400

    UserPinnedAchievement.query.filter_by(user_id=current_user.id).delete()

    for index, ua_id in enumerate(pinned_ids):
        db.session.add(UserPinnedAchievement(
            user_id=current_user.id,
            user_achievement_id=ua_id,
            pin_order=index + 1  # 1-5, per the model's UniqueConstraint on (user_id, pin_order)
        ))

    db.session.commit()
    return jsonify({'success': True})
