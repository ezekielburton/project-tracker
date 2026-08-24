"""
Profile blueprint — viewing (own and other users') and editing profile data.
Covers the profile page and its achievement display; auth and account
settings live in the auth module.
"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import User

profile_bp = Blueprint('profile', __name__, template_folder='../templates')


AVATAR_UPLOAD_FOLDER = os.path.join('app', 'static', 'avatars')
BANNER_UPLOAD_FOLDER = os.path.join('app', 'static', 'banners')
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}


def _save_profile_image(file, upload_folder):
    """
    Shared save logic for avatar/banner uploads. The browser always sends a
    JPEG blob it already cropped and compressed via Cropper.js, but we still
    validate server-side — never trust what the client claims to have sent.
    Returns the stored filename, or None if the file was rejected.
    """
    if not file or file.filename == '':
        return None

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    stored_filename = f'{uuid.uuid4().hex[:8]}.{ext}'
    os.makedirs(upload_folder, exist_ok=True)
    file.save(os.path.join(upload_folder, stored_filename))
    return stored_filename


def _format_earned_date(earned_at):
    """
    Formats a UTC earned_at datetime as 'Earned 3 Jun 2026', in Dubai local
    time. Uses the same fixed-offset timezone(timedelta(hours=4)) pattern
    as the dubai_time filter in app/__init__.py (ZoneInfo needs tzdata on
    Windows, per CLAUDE.md), and builds the "day month year" string by hand
    rather than with %-d, which isn't portable to Windows' strftime — same
    reason the birthday tag in profile.html does this manually.
    """
    if not earned_at:
        return None
    from datetime import timezone, timedelta
    dubai_tz = timezone(timedelta(hours=4))
    local = earned_at.replace(tzinfo=timezone.utc).astimezone(dubai_tz)
    return f'Earned {local.day} {local.strftime("%b")} {local.year}'


def _build_achievement_tile(achievement, user_achievement):
    """
    Builds the small dict the tile macro in profile.html needs for ONE
    earned achievement. Used for both the Recent tab and the Pinned tab
    (own profile), and for the pinned-only view on someone else's profile.

    Every achievement that reaches this function is already earned —
    pinning only ever references earned UserAchievement rows, and "recent"
    is filtered to earned_at IS NOT NULL before this is ever called. So
    unlike the full checklist below, there's no locked/hidden state to
    represent here — a hidden achievement that's been earned always fully
    reveals, same as any other.
    """
    return {
        'id': achievement.id,
        'name': achievement.name,
        'badge_image': achievement.badge_image,
        'badge_type': achievement.badge_type,
        'earned_display': _format_earned_date(user_achievement.earned_at),
    }


def _build_achievement_context(profile_user, is_own_profile):
    """
    Assembles every achievement-related value the profile template needs.
    Split out of view() since it's a meaningfully large chunk of query
    logic on its own — mirrors how projects_detail.py factors out
    standard_designers_by_deliverable rather than building it inline.

    Always returns pinned_tiles, recent_tiles, and achievement_checklist
    keys (empty list when not applicable) so the template never has to
    branch on whether a key exists at all — only on whether it's empty,
    and on is_own_profile for which sections to show in the first place.
    """
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
        # Visitors only ever see pinned tiles — no Recent tab, no expandable
        # checklist, no progress bars. If this user hasn't pinned anything,
        # the template shows an empty-state message rather than falling back
        # to their recent achievements.
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
    # Bulk-fetch this user's progress rows into a dict keyed by achievement_id
    # up front, instead of querying UserAchievement once per achievement
    # inside the loop below — avoids an N+1 query pattern as the achievement
    # catalogue grows.
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
            # Skip empty categories entirely — a category can have zero
            # achievements in it, and a heading with nothing underneath just
            # looks broken.
            continue
        rows = []
        for achievement in category_achievements:
            user_achievement = progress_by_achievement_id.get(achievement.id)
            progress = user_achievement.progress if user_achievement else 0
            earned_at = user_achievement.earned_at if user_achievement else None

            # Hidden + not yet earned = "???" with a lock icon, and NO
            # progress bar — showing a bar here would leak the threshold
            # and spoil the surprise is_hidden exists to protect. Once
            # earned, a hidden achievement is indistinguishable from any
            # other in this list.
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
    """
    Renders the profile page. No user_id in the URL = your own profile
    (matches the pre-split behavior exactly, so the existing sidebar link
    and any bookmarks to plain /profile keep working). A user_id renders
    that user's profile instead, in view-only mode.

    Uses get_actor() rather than current_user directly so that an admin
    emulating another user sees that user's own profile when they visit
    /profile with no id — consistent with how emulation is handled
    everywhere else in the app.
    """
    from app.modules.core.shared.models import RoleTitle, DEFAULT_ROLE_TITLES, UserDisplaySettings, UserAchievement, AchievementBorder
    from app.modules.core.shared.lib.utils import get_actor

    actor = get_actor()
    profile_user = User.query.get_or_404(user_id) if user_id is not None else actor
    is_own_profile = actor.id == profile_user.id

    # Fun title is always based on the profile being VIEWED, not the viewer —
    # visiting someone else's profile should show their title, not yours.
    role_title = RoleTitle.query.filter_by(role=profile_user.role).first()
    fun_title = role_title.title if role_title else DEFAULT_ROLE_TITLES.get(profile_user.role, '')

    # Active Rewards override the defaults above, based on profile_user's own
    # saved choices — NOT the viewer's. Visiting someone else's profile always
    # shows THEIR active title/border, same as their pinned achievements do.
    active_border_class = None
    display_settings = UserDisplaySettings.query.filter_by(user_id=profile_user.id).first()
    if display_settings:
        if display_settings.active_title_id:
            active_title_ua = UserAchievement.query.get(display_settings.active_title_id)
            # Defensive re-check, same reasoning as save_display_settings'
            # validation — an achievement could theoretically have been
            # edited to remove its reward_title after being set as active.
            if active_title_ua and active_title_ua.achievement.reward_title:
                fun_title = active_title_ua.achievement.reward_title

        if display_settings.active_border_id:
            border = AchievementBorder.query.get(display_settings.active_border_id)
            if border:
                active_border_class = border.css_class

    achievement_context = _build_achievement_context(profile_user, is_own_profile)

    # Customize context — only needed on own profile (badge picker + pin manager).
    # Reuses _build_account_achievement_context() which already assembles this data.
    customize_context = {}
    if is_own_profile:
        customize_context = _build_account_achievement_context(profile_user)

    return render_template(
        'profile/profile.html',
        profile_user=profile_user,
        is_own_profile=is_own_profile,
        fun_title=fun_title,
        active_border_class=active_border_class,
        customize_context=customize_context,
        **achievement_context
    )


@profile_bp.route('/profile/avatar', methods=['POST'])
@login_required
def upload_avatar():
    """
    Uploads always apply to current_user, never profile_user — you can
    only ever change your OWN avatar/banner/details/bio, regardless of
    whose profile page you happen to be looking at when you do it (in
    practice the edit controls that call these routes are only rendered
    at all when is_own_profile is true, but this route being current_user
    -scoped means that's a UI nicety, not the actual security boundary).
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    stored_filename = _save_profile_image(request.files['file'], AVATAR_UPLOAD_FOLDER)
    if not stored_filename:
        return jsonify({'success': False, 'error': 'Invalid file'}), 400

    # Delete the old avatar file from disk so replacing a photo doesn't
    # silently pile up orphaned files over time.
    old_filename = current_user.avatar_filename
    if old_filename:
        old_path = os.path.join(AVATAR_UPLOAD_FOLDER, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    current_user.avatar_filename = stored_filename
    db.session.commit()
    return jsonify({'success': True, 'url': url_for('static', filename=f'avatars/{stored_filename}')})


@profile_bp.route('/profile/banner', methods=['POST'])
@login_required
def upload_banner():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    stored_filename = _save_profile_image(request.files['file'], BANNER_UPLOAD_FOLDER)
    if not stored_filename:
        return jsonify({'success': False, 'error': 'Invalid file'}), 400

    old_filename = current_user.banner_filename
    if old_filename:
        old_path = os.path.join(BANNER_UPLOAD_FOLDER, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    current_user.banner_filename = stored_filename
    db.session.commit()
    return jsonify({'success': True, 'url': url_for('static', filename=f'banners/{stored_filename}')})


@profile_bp.route('/profile/details', methods=['POST'])
@login_required
def update_profile_details():
    """
    Saves the three fields editable from the profile page's "Edit Details"
    popup: name, favorite_food, birthday. Deliberately does NOT read a
    'role' or 'fun_title' key from the request even though those two fields
    are shown (disabled) in that same popup for context — role changes stay
    admin-only via the existing Admin Panel, and fun_title is derived from
    role elsewhere (RoleTitle table / DEFAULT_ROLE_TITLES fallback). Keeping
    this route ignorant of those keys means there's no code path here that
    could ever let a user grant themselves a different role, even if the
    request body were tampered with.
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    # Name is required — an empty name would break every place it's displayed
    # (sidebar dropdown, activity log entries, project assignment lists, etc.)
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400
    current_user.name = name

    # Favourite food is optional — store None rather than an empty string so
    # the profile template's "{% if profile_user.favorite_food %}" check
    # correctly hides the field when it's blank, instead of showing an empty pill.
    current_user.favorite_food = (data.get('favorite_food') or '').strip() or None

    # Birthday arrives as an HTML <input type="date"> value: 'yyyy-mm-dd', or
    # an empty string if the user cleared the field. Convert to a real Python
    # date for the DB column, or None to clear a previously-saved birthday.
    birthday_str = data.get('birthday')
    if birthday_str:
        try:
            current_user.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
        except ValueError:
            # Shouldn't happen from the date picker itself, but guards against
            # a hand-crafted request with a malformed date string.
            return jsonify({'success': False, 'error': 'Invalid birthday format'}), 400
    else:
        current_user.birthday = None

    db.session.commit()
    return jsonify({'success': True})


@profile_bp.route('/profile/bio', methods=['POST'])
@login_required
def update_profile_bio():
    """
    Saves the free-text bio shown on the profile page. Kept as its own tiny
    route rather than folded into update_profile_details() above, since it's
    edited from a separate inline control (pencil icon on the Bio card
    itself), not the combined Edit Details popup.
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    bio = (data.get('bio') or '').strip()

    # bio is an unbounded Text column in the DB, but the profile card has a
    # fixed layout — cap length here so a very long paste can't visually
    # break the card. Matches the textarea's maxlength="1000" in the template,
    # this is just the server-side backstop for that same rule.
    if len(bio) > 1000:
        return jsonify({'success': False, 'error': 'Bio must be 1000 characters or fewer'}), 400

    # Store None rather than an empty string when cleared, so the template's
    # "{{ profile_user.bio or 'No bio yet.' }}" fallback renders correctly.
    current_user.bio = bio or None
    db.session.commit()
    return jsonify({'success': True})

def _build_account_achievement_context(user):
    """
    Assembles everything the Account page's Active Rewards + pinning sections
    need: the dropdown choices for Active Rewards, the user's current
    selections (to pre-select those dropdowns), and the data the
    drag-and-drop pinning UI needs (every earned achievement, plus which ones
    are currently pinned and in what order).

    Lives in the profile module rather than auth: every achievement-domain
    read/write stays in one place, even though this data is rendered on the
    Account page (the auth module's account view), not the profile page.
    """
    from app.modules.core.shared.models import UserAchievement, UserDisplaySettings, UserPinnedAchievement, AchievementBorder

    # Every achievement this user has actually earned — the single source
    # every dropdown and the pinning UI below all filter down from. Ordered
    # by earned_at desc so "your most impressive/recent stuff" naturally
    # floats to the top of long lists.
    earned = (
        UserAchievement.query
        .filter(UserAchievement.user_id == user.id, UserAchievement.earned_at.isnot(None))
        .order_by(UserAchievement.earned_at.desc())
        .all()
    )

    # Title dropdown only offers achievements that actually unlock a title —
    # selecting one with reward_title = None would have nothing to display.
    title_choices = [ua for ua in earned if ua.achievement.reward_title]

    # Border dropdown: collect the distinct AchievementBorder rows unlocked
    # by anything in `earned`. A dict keyed by border.id both de-duplicates
    # (two earned achievements could reference the same border) and gives
    # us a stable list to iterate for the <select> options.
    border_choices = {}
    for ua in earned:
        if ua.achievement.border_id:
            border = AchievementBorder.query.get(ua.achievement.border_id)
            if border:
                border_choices[border.id] = border

    # Current selections, so the template can mark the right <option> as
    # selected — a brand new user has no row here at all yet, hence get()
    # returning None being a perfectly normal, expected case.
    display_settings = UserDisplaySettings.query.filter_by(user_id=user.id).first()

    # Fetched once, used two ways below: pinned_ids is just the id set (so
    # the template can filter pinned items OUT of the "Earned" column),
    # while pinned_achievements_ordered carries the actual UserAchievement
    # objects in pin_order — the "Pinned" column needs pin_order, not
    # earned_at order, and Jinja has no clean way to sort a list by
    # position in another list, so we do that sorting here in Python instead.
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
    """
    Saves the three Active Rewards selections (badge / title / border) as
    one upserted UserDisplaySettings row. Each incoming id is independently
    optional (null clears that slot back to the default) and independently
    validated — a request setting a valid badge but an invalid title
    shouldn't silently corrupt the badge selection too, so we validate
    everything BEFORE writing anything.
    """
    from app.modules.core.shared.models import UserDisplaySettings, UserAchievement, AchievementBorder

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    def _validated_user_achievement_id(key, require_reward_title=False):
        """
        Looks up data[key] as a UserAchievement id and returns it only if
        it's null (valid — clears the slot) OR it belongs to current_user
        AND is actually earned. Never trusts the client's claim that an id
        is theirs — re-checks user_id and earned_at against the DB every
        time. Returns (True, value) on success, (False, error_message) on
        failure, so the caller can bail out before writing anything.
        """
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

    # Border validation is separate: it's a direct AchievementBorder id,
    # not a UserAchievement id, and "earned" means "some achievement I've
    # earned references this border" rather than a direct ownership check.
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

    # Upsert — one row per user, per the model's unique=True on user_id.
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
    """
    Replaces the user's entire UserPinnedAchievement set in one go, based
    on an ordered list of user_achievement_ids sent from the drag-and-drop
    UI. Delete-all-then-recreate rather than diffing — pinned rows carry no
    state worth preserving beyond their order (unlike the Standard Brief
    Deliverable upsert pattern in CLAUDE.md, which exists specifically to
    preserve per-row status through an edit), so there's nothing to lose
    by replacing the set wholesale, and it sidesteps any need to reconcile
    adds/removes/reorders as three separate operations.
    """
    from app.modules.core.shared.models import UserAchievement, UserPinnedAchievement

    data = request.get_json(silent=True)
    if data is None or 'pinned_ids' not in data:
        return jsonify({'success': False, 'error': 'Invalid JSON'}), 400

    pinned_ids = data['pinned_ids']

    if not isinstance(pinned_ids, list) or len(pinned_ids) > 5:
        return jsonify({'success': False, 'error': 'Must be a list of at most 5 achievements'}), 400

    if len(pinned_ids) != len(set(pinned_ids)):
        return jsonify({'success': False, 'error': 'Duplicate achievement in pin list'}), 400

    # Validate every id belongs to this user and is actually earned, same
    # never-trust-the-client rule as the display settings route above.
    # Collected up front so a bad id anywhere in the list rejects the
    # whole request instead of silently dropping just that one entry.
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
