from flask import Blueprint, render_template, request, jsonify, abort, current_app
from flask_login import login_required
from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Project, ProjectNote, User
from app.modules.core.shared.lib.utils import log_activity, mark_project_activity_seen
from app.modules.core.shared.lib.users import active_users_query

project_notes_bp = Blueprint('project_notes', __name__, template_folder='../templates')

# Narrower video list than Reference Files' — must play inline in <video>.
_CHAT_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
_CHAT_VIDEO_EXTENSIONS = {'mp4', 'mov', 'webm', 'm4v'}
# Image cap is a backstop (client already compresses); video cap is the real limit.
_CHAT_IMAGE_MAX_BYTES = 10 * 1024 * 1024
_CHAT_VIDEO_MAX_BYTES = 16 * 1024 * 1024


def _save_chat_attachment(project, upload):
    """Validates and uploads one chat attachment to the NAS. Returns
    (True, (stored_filename, original_filename, type)) or (False, error_message)."""
    import uuid
    from app.modules.core.shared.services.nas import upload_app_file, build_chat_file_path

    original_filename = upload.filename
    ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else ''

    if ext in _CHAT_IMAGE_EXTENSIONS:
        attachment_type = 'image'
        max_bytes = _CHAT_IMAGE_MAX_BYTES
    elif ext in _CHAT_VIDEO_EXTENSIONS:
        attachment_type = 'video'
        max_bytes = _CHAT_VIDEO_MAX_BYTES
    else:
        return False, f'File type .{ext} is not supported here.'

    file_bytes = upload.read()
    if len(file_bytes) > max_bytes:
        label = 'Video' if attachment_type == 'video' else 'Image'
        return False, f'{label} is too large (max {max_bytes // (1024 * 1024)}MB).'

    # UUID-based filename — a busy chat can pull in "IMG_1234.jpg" from many
    # phones into the same folder, so plain filenames risk collisions.
    stored_filename = f'{uuid.uuid4().hex}.{ext}'
    nas_file_path = build_chat_file_path(project, stored_filename)
    nas_folder = nas_file_path.rsplit('/', 1)[0]
    try:
        upload_app_file(file_bytes, nas_folder, stored_filename)
    except RuntimeError as e:
        current_app.logger.error(f'Chat attachment upload failed for project {project.id}: {e}')
        return False, 'File could not be saved to storage. Please try again.'

    return True, (stored_filename, original_filename, attachment_type)


def _get_actor():
    # Emulation-aware: admin "viewing as" another user attributes actions to them.
    from flask import session
    from flask_login import current_user
    from app.modules.core.shared.models import User
    emulating_id = session.get('emulating_user_id')
    return User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user


def _can_manage_notes(project, actor):
    # Who's actually working on this project: CS lead, secondary CS, owner, designers, admin.
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
        or any(pd.user_id == actor.id for pd in project.assigned_designers)
    )

def _get_mentionable_users(project):
    """Concrete @-mentionable roster: CS lead, secondary CS, project owner,
    assigned designers. Excludes admin/management — too broad a set to mention."""
    seen_ids = set()
    users = []

    def _add(user):
        if user and user.id not in seen_ids:
            seen_ids.add(user.id)
            users.append(user)

    _add(project.cs_lead)
    for assignment in project.secondary_cs_assignments:
        _add(assignment.user)
    _add(project.project_owner)
    for pd in project.assigned_designers:
        _add(pd.designer)
    return users


def _is_designer(user):
    return user.role in ('designer', 'team_lead')

def _overlapping_site_visit(visit_user, start_at, end_at, exclude_id=None):
    from app.modules.core.shared.models import SiteVisit
    query = SiteVisit.query.filter(
        SiteVisit.user_id == visit_user.id,
        SiteVisit.start_at < end_at,
        SiteVisit.end_at > start_at,
    )
    if exclude_id:
        query = query.filter(SiteVisit.id != exclude_id)
    return query.first()


@project_notes_bp.route('/projects/<int:project_id>/overlay/notes')
@login_required
def overlay_notes(project_id):
    """Site Visits tab — notes now live in the chat drawer (see overlay_chat()
    below); URL kept as /overlay/notes so the existing JS call site still works."""
    from app.modules.core.shared.models import User
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    site_visits = sorted(project.site_visits, key=lambda v: v.created_at, reverse=True)
    designers = active_users_query().filter(
        User.role.in_(['designer', 'team_lead'])
    ).order_by(User.name).all()

    return render_template(
        'project_overlay/_overlay_notes.html',
        project=project, site_visits=site_visits,
        can_log_site_visit=_can_log_site_visit(actor),
        designers=designers,
        actor=actor,
    )


def _highlight_mentions(text, mentioned_users):
    """Wraps each mentioned user's "@Name" in a highlight span, escaping the rest.
    Matches on their current name; longest names checked first to avoid partial shadowing."""
    from markupsafe import Markup, escape
    if not text:
        return Markup('')
    if not mentioned_users:
        return escape(text)
    needles = sorted({f'@{u.name}' for u in mentioned_users}, key=len, reverse=True)
    pieces = []
    i = 0
    while i < len(text):
        matched = next((n for n in needles if text.startswith(n, i)), None)
        if matched:
            pieces.append(f'<span class="overlay-chat-mention">{escape(matched)}</span>')
            i += len(matched)
        else:
            pieces.append(str(escape(text[i])))
            i += 1
    return Markup(''.join(pieces))


def _build_chat_rows(notes, actor, is_admin):
    """Turns notes into template-ready rows: Dubai-local time, day_label (day
    dividers), is_own/can_delete (5-min self-delete window), reaction_groups
    (emoji -> count/reacted_by_me), and body_html (mentions highlighted)."""
    from datetime import datetime, timezone, timedelta
    from collections import OrderedDict
    dubai_tz = timezone(timedelta(hours=4))
    now_utc = datetime.utcnow()
    today_local = now_utc.replace(tzinfo=timezone.utc).astimezone(dubai_tz).date()

    all_mentioned_ids = set()
    for note in notes:
        if note.tags and note.tags.get('mentions'):
            all_mentioned_ids.update(note.tags['mentions'])
    mentioned_users_by_id = {}
    if all_mentioned_ids:
        mentioned_users_by_id = {u.id: u for u in User.query.filter(User.id.in_(all_mentioned_ids)).all()}

    def day_label(local_date):
        delta = (today_local - local_date).days
        if delta == 0:
            return 'Today'
        if delta == 1:
            return 'Yesterday'
        if 0 < delta < 7:
            return local_date.strftime('%A')
        return local_date.strftime('%d %b %Y')

    def build_reaction_groups(note):
        grouped = OrderedDict()
        for r in note.reactions:
            grouped.setdefault(r.emoji, []).append(r)
        return [
            {
                'emoji': emoji,
                'count': len(reactors),
                'reacted_by_me': any(r.user_id == actor.id for r in reactors),
            }
            for emoji, reactors in grouped.items()
        ]

    rows = []
    current_day = None
    for note in notes:
        local_dt = note.created_at.replace(tzinfo=timezone.utc).astimezone(dubai_tz)
        local_day = local_dt.date()
        is_own = note.author_id == actor.id
        can_delete = is_admin or (is_own and (now_utc - note.created_at) <= timedelta(minutes=5))
        note_mentioned_ids = (note.tags.get('mentions') or []) if note.tags else []
        note_mentioned_users = [mentioned_users_by_id[mid] for mid in note_mentioned_ids if mid in mentioned_users_by_id]
        rows.append({
            'note': note,
            'time': local_dt.strftime('%H:%M'),
            'day_label': day_label(local_day) if local_day != current_day else None,
            'is_own': is_own,
            'can_delete': can_delete,
            'reaction_groups': build_reaction_groups(note),
            'body_html': _highlight_mentions(note.body, note_mentioned_users) if note.body else None,
        })
        current_day = local_day
    return rows


@project_notes_bp.route('/projects/<int:project_id>/overlay/chat')
@login_required
def overlay_chat(project_id):
    """Persistent chat drawer — every ProjectNote for this project, oldest first."""
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    notes = ProjectNote.query.filter_by(project_id=project.id).order_by(ProjectNote.created_at.asc()).all()
    is_admin = actor.role in ('admin', 'management')
    # At most one pinned note per project (enforced in toggle_pin_note).
    pinned_note = next((n for n in notes if n.is_pinned), None)

    # Clears the Projects table's "new chat" dot for this project (26/27
    # Aug 2026, per Ezekiel) — deliberately its own watermark, separate
    # from overlay()'s "new updates" one in project_overlay.py, so opening
    # some other tab never silently marks unread chat messages as read.
    mark_project_activity_seen(project, actor, 'chat')

    return render_template(
        'project_overlay/_overlay_chat.html',
        project=project,
        chat_rows=_build_chat_rows(notes, actor, is_admin),
        pinned_note=pinned_note,
        can_manage_notes=_can_manage_notes(project, actor),
        actor=actor,
    )


@project_notes_bp.route('/projects/<int:project_id>/overlay/chat/mentionable')
@login_required
def chat_mentionable_users(project_id):
    """Backs the composer's @-mention picker. Excludes the actor themself."""
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_notes(project, actor):
        abort(403)
    users = [u for u in _get_mentionable_users(project) if u.id != actor.id]
    return jsonify({'users': [{'id': u.id, 'name': u.name} for u in users]})


@project_notes_bp.route('/projects/<int:project_id>/overlay/notes/create', methods=['POST'])
@login_required
def create_note(project_id):
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_manage_notes(project, actor):
        abort(403)

    # Attachments post multipart/form-data; plain text posts JSON. request.files
    # only populates on multipart, so that's what tells the two paths apart.
    upload = request.files.get('file')
    if upload and upload.filename:
        data = request.form
    else:
        data = request.get_json(silent=True) or {}

    body = (data.get('body') or '').strip()
    if not body and not (upload and upload.filename):
        return jsonify({'success': False, 'error': 'Note text is required.'}), 400

    # Only honoured when it points at a message in this same project.
    reply_to_id = data.get('reply_to_id')
    if reply_to_id:
        reply_to_note = ProjectNote.query.get(reply_to_id)
        if not reply_to_note or reply_to_note.project_id != project.id:
            reply_to_id = None

    attachment_filename = attachment_original_filename = attachment_type = None
    if upload and upload.filename:
        ok, result = _save_chat_attachment(project, upload)
        if not ok:
            return jsonify({'success': False, 'error': result}), 400
        attachment_filename, attachment_original_filename, attachment_type = result

    # Re-validated against the real mentionable set — never trust client ids outright.
    # Multipart form can't carry a real array, so it arrives JSON-encoded there.
    raw_mentioned_ids = data.get('mentioned_ids')
    if isinstance(raw_mentioned_ids, str):
        import json
        try:
            raw_mentioned_ids = json.loads(raw_mentioned_ids)
        except (ValueError, TypeError):
            raw_mentioned_ids = []
    mentioned_ids = []
    if raw_mentioned_ids:
        mentionable_ids = {u.id for u in _get_mentionable_users(project)}
        for raw_id in raw_mentioned_ids:
            try:
                mid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if mid in mentionable_ids and mid != actor.id and mid not in mentioned_ids:
                mentioned_ids.append(mid)

    note = ProjectNote(
        project_id=project.id, author_id=actor.id, body=body,
        file_link=(data.get('file_link') or '').strip() or None,
        reply_to_id=reply_to_id,
        attachment_filename=attachment_filename,
        attachment_original_filename=attachment_original_filename,
        attachment_type=attachment_type,
        tags={'mentions': mentioned_ids} if mentioned_ids else None,
    )
    db.session.add(note)
    db.session.commit()

    log_activity('note_added', f'{actor.name} added a note to "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    if mentioned_ids:
        from app.modules.core.shared.services.notifications import notify_of_chat_mention
        mentioned_users = User.query.filter(User.id.in_(mentioned_ids)).all()
        notify_of_chat_mention(note, project, mentioned_users, actor)

    return jsonify({'success': True, 'note_id': note.id})


@project_notes_bp.route('/projects/notes/<int:note_id>/attachment')
@login_required
def chat_attachment(note_id):
    """Serves a chat image/video inline so a bubble's <img>/<video> tag can
    point straight at this URL, instead of forcing a Save As dialog."""
    import io
    import mimetypes
    from flask import send_file
    from app.modules.core.shared.services.nas import download_app_file, build_chat_file_path

    note = ProjectNote.query.get_or_404(note_id)
    if not note.attachment_filename:
        abort(404)

    nas_path = build_chat_file_path(note.project, note.attachment_filename)
    try:
        file_bytes = download_app_file(nas_path)
    except RuntimeError as e:
        current_app.logger.error(f'Chat attachment download failed (note_id={note_id}): {e}')
        abort(502)

    mimetype = mimetypes.guess_type(note.attachment_original_filename or note.attachment_filename)[0] \
        or 'application/octet-stream'
    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=False,
        download_name=note.attachment_original_filename or note.attachment_filename,
    )

from datetime import datetime as _dt


def _can_log_site_visit(actor):
    # Admin, management, project owners, or Technical-team designers/leads.
    if actor.role in ('admin', 'management', 'project_owner'):
        return True
    return actor.role in ('designer', 'team_lead') and actor.team == 'Technical'


@project_notes_bp.route('/projects/<int:project_id>/overlay/site-visits/<int:visit_id>/delete', methods=['POST'])
@login_required
def delete_site_visit(project_id, visit_id):
    from app.modules.core.shared.models import SiteVisit
    visit = SiteVisit.query.get_or_404(visit_id)
    if visit.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not (_can_log_site_visit(actor) or actor.role in ('admin', 'management')):
        abort(403)

    db.session.delete(visit)
    db.session.commit()
    return jsonify({'success': True})


@project_notes_bp.route('/projects/<int:project_id>/overlay/site-visits/create', methods=['POST'])
@login_required
def create_site_visit(project_id):
    from app.modules.core.shared.models import SiteVisit, User

    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    if not _can_log_site_visit(actor):
        abort(403)

    data = request.get_json(silent=True) or {}

    visit_user = User.query.get(int(data['user_id'])) if data.get('user_id') else None
    if not visit_user or not _is_designer(visit_user):
        return jsonify({'success': False, 'error_type': 'invalid_designer',
                        'error': 'Please select a designer for this site visit.'}), 400

    try:
        start_at = _dt.fromisoformat(data.get('start_at'))
        end_at = _dt.fromisoformat(data.get('end_at'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error_type': 'invalid_range',
                        'error': 'Please enter a valid start and end time.'}), 400

    if end_at <= start_at:
        return jsonify({'success': False, 'error_type': 'invalid_range',
                        'error': 'Please ensure the end time is after the start time'}), 400

    location = (data.get('location') or '').strip()
    if not location:
        return jsonify({'success': False, 'error_type': 'invalid_location',
                        'error': 'Please enter a location name.'}), 400

    conflict = _overlapping_site_visit(visit_user, start_at, end_at)
    if conflict:
        return jsonify({
            'success': False, 'error_type': 'overlap',
            'error': 'This site visit conflicts with another site visit',
            'conflict': {
                'project_name': conflict.project.name,
                'start_at': conflict.start_at.strftime('%d %b %Y, %H:%M'),
                'end_at': conflict.end_at.strftime('%d %b %Y, %H:%M'),
                'location': conflict.location,
            },
        }), 409

    visit = SiteVisit(
        project_id=project.id, user_id=visit_user.id, start_at=start_at, end_at=end_at,
        location=location,
        location_link=(data.get('location_link') or '').strip() or None,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(visit)
    db.session.commit()

    log_activity('site_visit_logged', f'{actor.name} logged a site visit for {visit_user.name} on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True, 'visit_id': visit.id})

@project_notes_bp.route('/projects/<int:project_id>/overlay/notes/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_note(project_id, note_id):
    from datetime import datetime, timedelta
    note = ProjectNote.query.get_or_404(note_id)
    if note.project_id != project_id:
        abort(404)
    actor = _get_actor()
    is_admin = actor.role in ('admin', 'management')
    is_author = note.author_id == actor.id
    if not (is_admin or is_author):
        abort(403)

    # 5-minute self-delete window; admin/management exempt.
    if is_author and not is_admin and (datetime.utcnow() - note.created_at) > timedelta(minutes=5):
        return jsonify({'success': False, 'error': 'This message can no longer be deleted (5-minute window has passed).'}), 403

    # delete_app_file logs-and-swallows its own failures, so a NAS hiccup never blocks this.
    if note.attachment_filename:
        from app.modules.core.shared.services.nas import delete_app_file, build_chat_file_path
        delete_app_file(build_chat_file_path(note.project, note.attachment_filename))

    db.session.delete(note)
    db.session.commit()
    return jsonify({'success': True})


@project_notes_bp.route('/projects/<int:project_id>/overlay/notes/<int:note_id>/pin', methods=['POST'])
@login_required
def toggle_pin_note(project_id, note_id):
    """Pin/unpin a message. One pin per project — pinning a new message
    replaces whichever one was pinned before."""
    note = ProjectNote.query.get_or_404(note_id)
    if note.project_id != project_id:
        abort(404)
    actor = _get_actor()
    if not _can_manage_notes(note.project, actor):
        abort(403)

    if note.is_pinned:
        note.is_pinned = False
    else:
        ProjectNote.query.filter(
            ProjectNote.project_id == project_id,
            ProjectNote.id != note.id,
            ProjectNote.is_pinned.is_(True),
        ).update({'is_pinned': False})
        note.is_pinned = True
    db.session.commit()
    return jsonify({'success': True, 'is_pinned': note.is_pinned})


@project_notes_bp.route('/projects/notes/<int:note_id>/react', methods=['POST'])
@login_required
def toggle_reaction(note_id):
    """Add/replace/remove the caller's own reaction. Same emoji again removes it,
    a different emoji replaces it."""
    from app.modules.core.shared.models import ProjectNoteReaction
    note = ProjectNote.query.get_or_404(note_id)
    actor = _get_actor()
    if not _can_manage_notes(note.project, actor):
        abort(403)

    data = request.get_json(silent=True) or {}
    emoji = (data.get('emoji') or '').strip()
    if not emoji:
        return jsonify({'success': False, 'error': 'No emoji provided.'}), 400

    existing = ProjectNoteReaction.query.filter_by(note_id=note.id, user_id=actor.id).first()
    if existing and existing.emoji == emoji:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'success': True, 'reacted': False})

    if existing:
        existing.emoji = emoji
    else:
        db.session.add(ProjectNoteReaction(note_id=note.id, user_id=actor.id, emoji=emoji))
    db.session.commit()
    return jsonify({'success': True, 'reacted': True, 'emoji': emoji})


