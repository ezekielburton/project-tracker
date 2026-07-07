"""
Admin achievement management — Phase 7 of the achievement system.

Mirrors app/routes/admin.py's conventions exactly, since this is another
admin-only JSON API feeding a section of the same embedded admin panel in
base.html (no separate page/template — see admin-section-sounds for the
precedent this follows): local admin_required decorator (JSON 403, not an
HTML abort page, since every route here is called via fetch()), GET
returns a plain list of dicts, POST creates, PATCH edits, DELETE removes.
"""
import os
import uuid
from functools import wraps
from flask import Blueprint, jsonify, url_for, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models import Achievement, AchievementCategory, AchievementBorder, UserAchievement
from app.utils import log_activity

admin_achievements_bp = Blueprint('admin_achievements', __name__)


def admin_required(f):
    """
    Duplicated from admin.py rather than imported — both are tiny, and
    importing across sibling route modules for a 6-line decorator isn't
    worth the coupling. If this ever needs to change, check admin.py too.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        return f(*args, **kwargs)
    return decorated


ACHIEVEMENT_UPLOAD_FOLDER = os.path.join('app', 'static', 'achievements')
ALLOWED_BADGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}  # gif included — animated badges may want an animated source image

# The ONLY trigger_event values that actually do anything — every call site
# in the app that fires check_achievements() is listed in CLAUDE.md's Phase
# 2 spec. Hardcoded as a dropdown (rather than a free-text field) specifically
# because the Achievement model's own docstring calls out the risk: "a typo
# here silently meaning this achievement never fires." A dropdown of exactly
# these seven makes that typo impossible.
VALID_TRIGGER_EVENTS = [
    'project_submitted', 'project_approved', 'bug_submitted',
    'feature_submitted', 'blog_comment', 'upvote_given', 'user_login',
]


def _save_badge_image(file):
    """Same shape as profile.py's _save_profile_image — validates server-side, returns stored filename or None."""
    if not file or file.filename == '':
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_BADGE_EXTENSIONS:
        return None
    stored_filename = f'{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}'
    os.makedirs(ACHIEVEMENT_UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(ACHIEVEMENT_UPLOAD_FOLDER, stored_filename))
    return stored_filename


def _achievement_to_dict(a):
    return {
        'id': a.id,
        'category_id': a.category_id,
        'name': a.name,
        'description': a.description,
        'trigger_event': a.trigger_event,
        'threshold': a.threshold,
        'is_hidden': a.is_hidden,
        'badge_image': a.badge_image,
        'badge_url': url_for('static', filename=f'achievements/{a.badge_image}') if a.badge_image else None,
        'badge_type': a.badge_type,
        'reward_title': a.reward_title,
        'title_animated': a.title_animated,
        'border_id': a.border_id,
        'display_order': a.display_order,
    }


# ─────────────────────────── Categories ────────────────────────────────

@admin_achievements_bp.route('/admin/api/achievement-categories', methods=['GET'])
@login_required
@admin_required
def list_achievement_categories():
    """
    Powers the whole Achievements tab in one call: every category, each
    with its achievements nested inside, both already in display order.
    Avoids a second round-trip just to then fetch achievements per category.
    """
    categories = AchievementCategory.query.order_by(AchievementCategory.display_order).all()
    result = []
    for cat in categories:
        achievements = Achievement.query.filter_by(category_id=cat.id).order_by(Achievement.display_order).all()
        result.append({
            'id': cat.id,
            'name': cat.name,
            'icon': cat.icon,
            'display_order': cat.display_order,
            'achievements': [_achievement_to_dict(a) for a in achievements],
        })
    return jsonify(result)


@admin_achievements_bp.route('/admin/api/achievement-categories', methods=['POST'])
@login_required
@admin_required
def create_achievement_category():
    """
    Not in the original Phase 7 spec (which only mentions categories being
    reorderable), but Achievement.category_id is a required FK — there's no
    way to create an achievement at all without this existing first.
    """
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Category name is required'}), 400

    # New categories go last — display_order = current max + 1. Admins
    # reorder via drag afterward if they want it elsewhere.
    max_order = db.session.query(db.func.max(AchievementCategory.display_order)).scalar() or 0

    category = AchievementCategory(name=name, icon=(data.get('icon') or '').strip() or None, display_order=max_order + 1)
    db.session.add(category)
    db.session.commit()

    log_activity('achievement_category_added', f'{current_user.name} added achievement category "{name}"',
                 user=current_user, entity_type='achievement_category', entity_name=name, entity_id=category.id)
    return jsonify({'success': True, 'category': {'id': category.id, 'name': category.name, 'icon': category.icon}})


@admin_achievements_bp.route('/admin/api/achievement-categories/<int:category_id>', methods=['PATCH'])
@login_required
@admin_required
def update_achievement_category(category_id):
    """Edit a category's name and/or icon."""
    category = AchievementCategory.query.get_or_404(category_id)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Category name is required'}), 400

    category.name = name
    category.icon = (data.get('icon') or '').strip() or None
    db.session.commit()

    log_activity('achievement_category_edited', f'{current_user.name} edited achievement category "{name}"',
                 user=current_user, entity_type='achievement_category', entity_name=name, entity_id=category.id)
    return jsonify({'success': True, 'category': {'id': category.id, 'name': category.name, 'icon': category.icon}})


@admin_achievements_bp.route('/admin/api/achievement-categories/<int:category_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_achievement_category(category_id):
    """
    Blocks the delete if the category still has achievements in it, rather
    than cascading — same "hard block, clear error" pattern CLAUDE.md
    documents for user deletion (e.g. "user is CS Lead ... returns a clear
    error"). Achievement.category_id is NOT NULL, so silently cascading
    would destroy earned-achievement history for every user who'd earned
    something in this category; forcing the admin to move or delete those
    achievements first is the safer default.
    """
    category = AchievementCategory.query.get_or_404(category_id)
    name = category.name

    remaining = Achievement.query.filter_by(category_id=category_id).count()
    if remaining > 0:
        return jsonify({
            'success': False,
            'error': f'Cannot delete "{name}" — it still has {remaining} achievement(s) in it. Move or delete those first.'
        }), 400

    db.session.delete(category)
    db.session.commit()

    log_activity('achievement_category_removed', f'{current_user.name} removed achievement category "{name}"',
                 user=current_user, entity_type='achievement_category', entity_name=name, entity_id=category_id)
    return jsonify({'success': True})


@admin_achievements_bp.route('/admin/api/achievement-categories/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_achievement_categories():
    """Body: {'category_ids': [id, id, ...]} in the new display order — matches the drag-and-drop accordion order."""
    data = request.get_json(silent=True) or {}
    category_ids = data.get('category_ids')
    if not isinstance(category_ids, list):
        return jsonify({'success': False, 'error': 'Invalid category_ids'}), 400

    for index, cat_id in enumerate(category_ids):
        AchievementCategory.query.filter_by(id=cat_id).update({'display_order': index})
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────── Achievements ──────────────────────────────

@admin_achievements_bp.route('/admin/api/achievements', methods=['POST'])
@login_required
@admin_required
def create_achievement():
    """
    Multipart form (not JSON) — this route accepts an optional badge image
    file alongside the text fields, same reasoning as profile.py's avatar/
    banner uploads. Booleans arrive as the literal strings 'true'/'false'
    (the admin panel JS sends them explicitly rather than relying on
    checkbox-only-present-when-checked FormData quirks).
    """
    name = (request.form.get('name') or '').strip()
    category_id = request.form.get('category_id')
    trigger_event = request.form.get('trigger_event')
    threshold = request.form.get('threshold')

    if not name:
        return jsonify({'success': False, 'error': 'Achievement name is required'}), 400
    if not category_id or not AchievementCategory.query.get(category_id):
        return jsonify({'success': False, 'error': 'A valid category is required'}), 400
    if trigger_event not in VALID_TRIGGER_EVENTS:
        return jsonify({'success': False, 'error': 'Invalid trigger event'}), 400
    try:
        threshold = int(threshold)
        if threshold < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Threshold must be a positive number'}), 400

    border_id = request.form.get('border_id') or None
    if border_id and not AchievementBorder.query.get(border_id):
        return jsonify({'success': False, 'error': 'Invalid border selected'}), 400

    badge_image = None
    if 'badge_file' in request.files and request.files['badge_file'].filename:
        badge_image = _save_badge_image(request.files['badge_file'])
        if badge_image is None:
            return jsonify({'success': False, 'error': 'Invalid badge image file type'}), 400

    max_order = db.session.query(db.func.max(Achievement.display_order)).filter_by(category_id=category_id).scalar() or 0

    achievement = Achievement(
        category_id=category_id,
        name=name,
        description=(request.form.get('description') or '').strip() or None,
        trigger_event=trigger_event,
        threshold=threshold,
        is_hidden=(request.form.get('is_hidden') == 'true'),
        badge_image=badge_image,
        badge_type='animated' if request.form.get('badge_type') == 'animated' else 'static',
        reward_title=(request.form.get('reward_title') or '').strip() or None,
        title_animated=(request.form.get('title_animated') == 'true'),
        border_id=border_id,
        display_order=max_order + 1,
    )
    db.session.add(achievement)
    db.session.commit()

    log_activity('achievement_added', f'{current_user.name} added achievement "{name}"',
                 user=current_user, entity_type='achievement', entity_name=name, entity_id=achievement.id)
    return jsonify({'success': True, 'achievement': _achievement_to_dict(achievement)})


@admin_achievements_bp.route('/admin/api/achievements/<int:achievement_id>', methods=['PATCH'])
@login_required
@admin_required
def update_achievement(achievement_id):
    """
    Edits an existing achievement. The badge image is optional on edit —
    unlike create, where a missing file just means "no image," here a
    missing file means "keep whatever's already saved." Only a new file
    replaces it (and the old file on disk is deleted, same as
    profile.py's avatar-replace logic).
    """
    achievement = Achievement.query.get_or_404(achievement_id)

    name = (request.form.get('name') or '').strip()
    trigger_event = request.form.get('trigger_event')
    threshold = request.form.get('threshold')

    if not name:
        return jsonify({'success': False, 'error': 'Achievement name is required'}), 400
    if trigger_event not in VALID_TRIGGER_EVENTS:
        return jsonify({'success': False, 'error': 'Invalid trigger event'}), 400
    try:
        threshold = int(threshold)
        if threshold < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Threshold must be a positive number'}), 400

    border_id = request.form.get('border_id') or None
    if border_id and not AchievementBorder.query.get(border_id):
        return jsonify({'success': False, 'error': 'Invalid border selected'}), 400

    if 'badge_file' in request.files and request.files['badge_file'].filename:
        new_filename = _save_badge_image(request.files['badge_file'])
        if new_filename is None:
            return jsonify({'success': False, 'error': 'Invalid badge image file type'}), 400
        old_path = os.path.join(ACHIEVEMENT_UPLOAD_FOLDER, achievement.badge_image) if achievement.badge_image else None
        if old_path and os.path.exists(old_path):
            os.remove(old_path)
        achievement.badge_image = new_filename

    achievement.name = name
    achievement.description = (request.form.get('description') or '').strip() or None
    achievement.trigger_event = trigger_event
    achievement.threshold = threshold
    achievement.is_hidden = (request.form.get('is_hidden') == 'true')
    achievement.badge_type = 'animated' if request.form.get('badge_type') == 'animated' else 'static'
    achievement.reward_title = (request.form.get('reward_title') or '').strip() or None
    achievement.title_animated = (request.form.get('title_animated') == 'true')
    achievement.border_id = border_id

    db.session.commit()

    log_activity('achievement_edited', f'{current_user.name} edited achievement "{name}"',
                 user=current_user, entity_type='achievement', entity_name=name, entity_id=achievement.id)
    return jsonify({'success': True, 'achievement': _achievement_to_dict(achievement)})


@admin_achievements_bp.route('/admin/api/achievements/<int:achievement_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_achievement(achievement_id):
    """
    Deletes the achievement catalogue entry AND every user's progress
    toward it (UserAchievement rows) — there's no meaningful "achievement
    you can't see the definition of but still have progress on" state to
    preserve. Matches the cascade-then-delete pattern CLAUDE.md documents
    for user deletion: clear out dependents first, then the row itself.
    """
    achievement = Achievement.query.get_or_404(achievement_id)
    name = achievement.name

    if achievement.badge_image:
        path = os.path.join(ACHIEVEMENT_UPLOAD_FOLDER, achievement.badge_image)
        if os.path.exists(path):
            os.remove(path)

    UserAchievement.query.filter_by(achievement_id=achievement_id).delete()
    db.session.delete(achievement)
    db.session.commit()

    log_activity('achievement_removed', f'{current_user.name} removed achievement "{name}"',
                 user=current_user, entity_type='achievement', entity_name=name, entity_id=achievement_id)
    return jsonify({'success': True})


@admin_achievements_bp.route('/admin/api/achievements/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_achievements():
    """Body: {'achievement_ids': [id, id, ...]} — all within ONE category (the accordion section being reordered)."""
    data = request.get_json(silent=True) or {}
    achievement_ids = data.get('achievement_ids')
    if not isinstance(achievement_ids, list):
        return jsonify({'success': False, 'error': 'Invalid achievement_ids'}), 400

    for index, ach_id in enumerate(achievement_ids):
        Achievement.query.filter_by(id=ach_id).update({'display_order': index})
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────── Borders ───────────────────────────────────

@admin_achievements_bp.route('/admin/api/achievement-borders', methods=['GET'])
@login_required
@admin_required
def list_achievement_borders():
    borders = AchievementBorder.query.order_by(AchievementBorder.name).all()
    return jsonify([{'id': b.id, 'name': b.name, 'css_class': b.css_class} for b in borders])


@admin_achievements_bp.route('/admin/api/achievement-borders', methods=['POST'])
@login_required
@admin_required
def create_achievement_border():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    css_class = (data.get('css_class') or '').strip()
    if not name or not css_class:
        return jsonify({'success': False, 'error': 'Both name and CSS class are required'}), 400

    border = AchievementBorder(name=name, css_class=css_class)
    db.session.add(border)
    db.session.commit()

    log_activity('achievement_border_added', f'{current_user.name} added achievement border "{name}"',
                 user=current_user, entity_type='achievement_border', entity_name=name, entity_id=border.id)
    return jsonify({'success': True, 'border': {'id': border.id, 'name': border.name, 'css_class': border.css_class}})


@admin_achievements_bp.route('/admin/api/achievement-borders/<int:border_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_achievement_border(border_id):
    """
    Blocked if any Achievement still references this border — same
    reasoning as category deletion. UserDisplaySettings.active_border_id
    also points at borders, but that FK is nullable and not our concern
    here: if a border in active use elsewhere got deleted anyway, the
    active_badge_image()-style lookups just find nothing and render
    without it, rather than crashing — but blocking at the achievement
    level catches the far more common case up front.
    """
    border = AchievementBorder.query.get_or_404(border_id)
    name = border.name

    in_use = Achievement.query.filter_by(border_id=border_id).count()
    if in_use > 0:
        return jsonify({
            'success': False,
            'error': f'Cannot delete "{name}" — {in_use} achievement(s) still reward this border.'
        }), 400

    db.session.delete(border)
    db.session.commit()

    log_activity('achievement_border_removed', f'{current_user.name} removed achievement border "{name}"',
                 user=current_user, entity_type='achievement_border', entity_name=name, entity_id=border_id)
    return jsonify({'success': True})
