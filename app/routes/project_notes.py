# app/routes/project_notes.py
from flask import Blueprint, render_template, request, jsonify, abort, current_app
from flask_login import login_required
from app import db
from app.models import Project, ProjectNote, User
from app.utils import log_activity

project_notes_bp = Blueprint('project_notes', __name__)

# Chat attachments (Phase 3 — images/videos, 21 Aug 2026). Video list is
# deliberately narrower than Reference Files' (project_overlay.py) — this
# has to actually play inline in a <video> tag in-browser, not just be
# downloadable, so formats Chrome won't natively play (avi, wmv) are left
# off rather than uploaded and then silently unplayable in the thread.
_CHAT_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
_CHAT_VIDEO_EXTENSIONS = {'mp4', 'mov', 'webm', 'm4v'}
# Images are compressed client-side before they ever reach this route (see
# project_chat_panel.js) — this is just a server-side backstop, not the
# real limit. Video gets no compression at all (Ezekiel, 21 Aug 2026:
# "Hard cap for videos is fine"), so 16MB here IS the real limit.
_CHAT_IMAGE_MAX_BYTES = 10 * 1024 * 1024
_CHAT_VIDEO_MAX_BYTES = 16 * 1024 * 1024


def _save_chat_attachment(project, upload):
    """Validates and uploads one chat attachment to the NAS. Returns
    (True, (stored_filename, original_filename, attachment_type)) on
    success, or (False, error_message) on failure — never raises, so
    create_note() can turn a failure straight into a 400 response without
    its own try/except around this call."""
    import uuid
    from app.nas import upload_app_file, build_chat_file_path

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

    # UUID-based stored filename — unlike Reference Files (which keeps the
    # original filename as-is, one project's files uploaded by a handful of
    # CS/designers), a busy project chat can pull in "IMG_1234.jpg" from
    # many different people's phones into the SAME shared per-project NAS
    # folder (see build_chat_file_path) — collisions are a real risk here.
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
    # Same emulation-aware pattern used everywhere else in the overlay routes
    # (project_overlay.py, project_preproduction.py) — admins can "view as"
    # another user, and every action should attribute to whoever they're
    # emulating, not the literal logged-in admin account.
    from flask import session
    from flask_login import current_user
    from app.models import User
    emulating_id = session.get('emulating_user_id')
    return User.query.get(emulating_id) if (emulating_id and current_user.role == 'admin') else current_user


def _can_manage_notes(project, actor):
    # Same "who's actually working on this project" set used for Reference
    # Files elsewhere — CS lead, secondary CS, assigned project owner, or
    # admin/management. Broad on purpose: a note is low-stakes, unlike
    # deleting a deliverable.
    secondary_cs_ids = {a.user_id for a in project.secondary_cs_assignments}
    return (
        actor.role in ('admin', 'management')
        or actor.id == project.cs_lead_id
        or actor.id in secondary_cs_ids
        or (actor.role == 'project_owner' and actor.id == project.project_owner_id)
        or any(pd.user_id == actor.id for pd in project.assigned_designers)
    )

def _get_mentionable_users(project):
    """The concrete set of people you can @-mention in this project's chat
    (Phase 5 — mentions, 21 Aug 2026): CS lead, secondary CS, project
    owner, and assigned designers — same roster _can_manage_notes checks
    a single actor against, just resolved to actual User rows instead of
    a membership test. Deliberately does NOT include "any admin/
    management" — that's every admin in the company, not people actually
    on this project, and notify_* functions elsewhere in this app always
    build an explicit per-project recipient list rather than querying by
    role for exactly this reason."""
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


# becomes:
def _is_designer(user):
    return user.role in ('designer', 'team_lead')

def _overlapping_site_visit(visit_user, start_at, end_at, exclude_id=None):
    from app.models import SiteVisit
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
    """Site Visits tab (M10 chat redesign, 21 Aug 2026) — this used to also
    render a merged Notes feed; notes now live in the persistent chat
    drawer instead (see overlay_chat() below), so this route only builds
    the site-visit log + logging form. URL kept as /overlay/notes rather
    than renamed to /overlay/site-visits so the existing JS call site
    (project_list.js's loadNotesSection) didn't need to change."""
    from app.models import User
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    site_visits = sorted(project.site_visits, key=lambda v: v.created_at, reverse=True)
    designers = User.query.filter(
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
    """Wraps every literal "@Name" occurrence — for a user actually
    recorded in this note's tags['mentions'], not just any "@word" — in a
    highlight span, HTML-escaping everything else (Phase 5 — mentions, 21
    Aug 2026). Matches on each mentioned user's CURRENT name, not
    whatever was typed at send time — same "always derive display text
    from the live User row" convention this app uses everywhere else, so
    a later name change re-renders correctly instead of freezing the old
    name into the message forever.

    Plain substring matching, not regex — a handful of names per message,
    no user-controlled pattern involved, so this is simpler and safer
    than building a dynamic regex out of names that could contain regex
    metacharacters. Longest names checked first so e.g. "@Ali" can't
    shadow a match inside "@Ali Khan" when both are mentioned."""
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
    """Turns a chronological ProjectNote list into template-ready rows —
    each note's Dubai-local send time, plus a day_label set only on the
    first message of a new local day (None the rest of that day), so
    _overlay_chat.html can render a WhatsApp-style day divider with one
    flat loop instead of a nested group-by in Jinja. Dubai time, not raw
    UTC, so "Today"/"Yesterday" match what the person actually sees as
    today — same fixed-offset convention profile.py's _format_earned_date
    already uses for the same reason.

    Also computes, per row, is_own (which side the bubble renders on) and
    can_delete — the 5-minute self-delete window (message-interactions
    adjustment, 21 Aug 2026): an author can delete their own message only
    within 5 minutes of sending it; admin/management stay exempt, same
    override every other permission gate in this file already makes.

    reaction_groups (Phase 4, 21 Aug 2026) — note.reactions (one row per
    person per emoji, see ProjectNoteReaction) collapsed into one entry
    per distinct emoji with a count and whether the CURRENT actor is one
    of the reactors, so _overlay_chat.html can render WhatsApp-style
    "👍 3" chips under a bubble with one flat loop instead of grouping in
    Jinja. Insertion order preserved (first person to use an emoji decides
    where its chip sits), matching how reactions visually settle in most
    chat apps rather than re-sorting on every reload.

    body_html (Phase 5 — mentions, 21 Aug 2026) — note.body with any
    "@Name" the sender actually mentioned (note.tags['mentions'], set by
    create_note()) wrapped for highlighting; see _highlight_mentions().
    All mentioned users across the whole thread are fetched in one query
    up front rather than per-row, same batch-not-N+1 shape as everything
    else in this file that touches a relationship per note."""
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
    """Persistent chat drawer (M10 chat redesign) — replaces the old Notes
    card. Every ProjectNote for this project, oldest first (a chat thread
    reads top-to-bottom with the newest message at the bottom — the
    opposite order the old merged Notes feed used)."""
    project = Project.query.get_or_404(project_id)
    actor = _get_actor()
    notes = ProjectNote.query.filter_by(project_id=project.id).order_by(ProjectNote.created_at.asc()).all()
    is_admin = actor.role in ('admin', 'management')
    # Pinned strip — at most one note per project (enforced in
    # toggle_pin_note), found from the same already-fetched notes list
    # rather than a second query.
    pinned_note = next((n for n in notes if n.is_pinned), None)

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
    """Backs the composer's @-mention picker (Phase 5, 21 Aug 2026) —
    fetched once by project_chat_panel.js when the drawer opens and
    filtered client-side as you type, same shape as any other typeahead.
    The actor themself is left off the list (mentioning yourself isn't
    useful) but everyone else is returned regardless of whether they've
    sent a message here before."""
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

    # Attachments (Phase 3, 21 Aug 2026) post as multipart/form-data so the
    # raw file bytes can ride alongside the other fields; a plain text
    # message still posts JSON exactly as before. request.files only gets
    # populated on a multipart request, so that's what tells the two paths
    # apart — everything below reads from `data` either way.
    upload = request.files.get('file')
    if upload and upload.filename:
        data = request.form
    else:
        data = request.get_json(silent=True) or {}

    body = (data.get('body') or '').strip()
    if not body and not (upload and upload.filename):
        return jsonify({'success': False, 'error': 'Note text is required.'}), 400

    # Reply-to (WhatsApp-style quote, 21 Aug 2026) — only honoured when it
    # actually points at a message in this same project; a stale/cross-
    # project id (e.g. leftover composer state from a different overlay)
    # is silently dropped rather than failing the whole send over it.
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

    # @-mentions (Phase 5, 21 Aug 2026) — the composer sends back whichever
    # user ids it inserted "@Name" text for (project_chat_panel.js already
    # drops a mention client-side if its "@Name" text got deleted before
    # send). Re-validated against the project's real mentionable set here
    # rather than trusted outright — a stale/tampered id should silently
    # drop, not notify or store someone who isn't actually on this project.
    # A plain multipart form can't carry a real array, so the attachment
    # path sends it as a JSON-encoded string instead; the plain-JSON path
    # already gets a real list from request.get_json().
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
        from app.notifications import notify_of_chat_mention
        mentioned_users = User.query.filter(User.id.in_(mentioned_ids)).all()
        notify_of_chat_mention(note, project, mentioned_users, actor)

    return jsonify({'success': True, 'note_id': note.id})


@project_notes_bp.route('/projects/notes/<int:note_id>/attachment')
@login_required
def chat_attachment(note_id):
    """Serves a chat image/video inline (as_attachment=False) so a bubble's
    <img>/<video> tag can point straight at this URL — same NAS proxy-
    download shape as download_project_file (project_overlay.py), just
    inline instead of forcing a Save As dialog."""
    import io
    import mimetypes
    from flask import send_file
    from app.nas import download_app_file, build_chat_file_path

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

# app/routes/project_notes.py (continued)

from datetime import datetime as _dt


def _can_log_site_visit(actor):
    # management, technical designers/team leads, or project owners — per
    # Ezekiel. Admin included too, matching every other permission gate in
    # this codebase (admin is always a superset elsewhere) — flag this if
    # you actually want admin excluded, easy one-line change.
    if actor.role in ('admin', 'management', 'project_owner'):
        return True
    return actor.role in ('designer', 'team_lead') and actor.team == 'Technical'


@project_notes_bp.route('/projects/<int:project_id>/overlay/site-visits/<int:visit_id>/delete', methods=['POST'])
@login_required
def delete_site_visit(project_id, visit_id):
    from app.models import SiteVisit
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
    from app.models import SiteVisit, User

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
        location=(data.get('location') or '').strip() or None,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(visit)
    db.session.commit()

    log_activity('site_visit_logged', f'{actor.name} logged a site visit for {visit_user.name} on "{project.name}"',
                 user=actor, entity_type='project', entity_name=project.name, entity_id=project.id)

    return jsonify({'success': True, 'visit_id': visit.id})

# app/routes/project_notes.py (continued)

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

    # 5-minute self-delete window (message-interactions adjustment, 21 Aug
    # 2026) — WhatsApp's "delete for everyone" cutoff. Admin/management
    # stay exempt, same override every other gate in this file makes.
    if is_author and not is_admin and (datetime.utcnow() - note.created_at) > timedelta(minutes=5):
        return jsonify({'success': False, 'error': 'This message can no longer be deleted (5-minute window has passed).'}), 403

    # Clean up the NAS file too, not just the DB row — delete_app_file
    # already logs-and-swallows any failure internally (see its docstring
    # in app/nas.py), so a NAS hiccup here never blocks deleting the
    # message itself.
    if note.attachment_filename:
        from app.nas import delete_app_file, build_chat_file_path
        delete_app_file(build_chat_file_path(note.project, note.attachment_filename))

    db.session.delete(note)
    db.session.commit()
    return jsonify({'success': True})


@project_notes_bp.route('/projects/<int:project_id>/overlay/notes/<int:note_id>/pin', methods=['POST'])
@login_required
def toggle_pin_note(project_id, note_id):
    """Pin/unpin a message to the top of the chat thread (message-
    interactions adjustment, 21 Aug 2026) — toggled from the same
    dropdown as Reply/Copy/Delete, or from the pinned strip's own chevron
    menu, gated the same as sending a note (not restricted to the
    message's own author, so anyone who can chat in this project can pin
    something worth surfacing).

    One pin per project at a time (Ezekiel, 21 Aug 2026) — pinning a new
    message replaces whichever one was pinned before, same as WhatsApp's
    single-pin-per-chat behaviour. Only matters on the way IN: unpinning
    is always just clearing this one note's own flag."""
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
    """Add/replace/remove the caller's own reaction on a message (Phase 4,
    21 Aug 2026) — real backend behind the quick-react popover, which
    until now only opened/closed as a UI-only provision. Toggle semantics:
    the same emoji again removes your reaction, a different emoji
    replaces it, no existing reaction creates one — one reaction per
    person per message, enforced by ProjectNoteReaction's unique
    constraint rather than checked here. Gated the same as sending/pinning
    a note (not restricted to the message's own author)."""
    from app.models import ProjectNoteReaction
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


