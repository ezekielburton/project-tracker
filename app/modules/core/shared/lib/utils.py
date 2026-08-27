import re as _re
from html import unescape as _unescape

def file_type_label(ext):
    """Return a human-readable label for a file extension.

    Used in activity log entries so they read like
    "Rehan added an image as a reference file to 'Project X'"
    instead of exposing raw filenames.
    """
    ext = (ext or '').lower()
    if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'}:
        return 'an image'
    if ext == 'pdf':
        return 'a PDF'
    if ext in {'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'txt', 'csv'}:
        return 'a document'
    if ext in {'mp4', 'mov', 'avi', 'webm', 'mkv', 'wmv', 'm4v'}:
        return 'a video'
    if ext == 'zip':
        return 'a ZIP file'
    if ext == 'dwg':
        return 'a DWG file'
    return 'a file'


def strip_html(html_text):
    """Strip HTML tags and decode entities for use in plain-text contexts
    (notifications, activity logs). Rich-text fields may contain <img> tags
    and other markup that must not leak into notification strings."""
    if not html_text:
        return ''
    text = _re.sub(r'<[^>]+>', '', html_text)
    text = _unescape(text)
    return ' '.join(text.split())


def get_actor():
    """Return the effective acting user.

    When an admin is emulating another user, actions like posting comments
    or submitting requests should be recorded as that user, not the admin.
    Admin-only write routes (delete, publish, status change) should use
    current_user directly — they don't call this helper.
    """
    from flask import session
    from flask_login import current_user
    from app.modules.core.shared.models import User
    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        return User.query.get(emulating_id)
    return current_user

def mark_project_activity_seen(project, user, kind):
    """Advances one of a user's two Projects-table unread watermarks for
    this project (26/27 Aug 2026, per Ezekiel — the table's per-row
    "new updates"/"new chat" dots; see ProjectActivitySeen's docstring in
    core/shared/models/projects.py for the full design).

    kind is 'update' or 'chat'. Callers: project_overlay.py's overlay()
    route (kind='update', fires on opening the overlay at all) and
    project_notes.py's overlay_chat() route (kind='chat', fires only on
    opening the Chat drawer specifically) — kept as two independent calls
    rather than one shared watermark, per Ezekiel's call that staff need
    to clear those two dots separately.

    Upserts rather than requiring a pre-existing row, and is deliberately
    best-effort like log_activity above — a failure here should never
    break the page it's called from, it just means the dot might not
    clear until the next successful visit."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectActivitySeen
    from datetime import datetime

    column = {'update': 'last_seen_update_at', 'chat': 'last_seen_chat_at'}[kind]
    try:
        seen = ProjectActivitySeen.query.filter_by(project_id=project.id, user_id=user.id).first()
        if not seen:
            seen = ProjectActivitySeen(project_id=project.id, user_id=user.id)
            db.session.add(seen)
        setattr(seen, column, datetime.utcnow())
        db.session.commit()
    except Exception:
        db.session.rollback()
        import traceback
        traceback.print_exc()


def log_activity(action, description, user=None, entity_type=None, entity_name=None, entity_id=None, changes=None):
    """description stays the free-text sentence shown everywhere (dashboard's
    What Changed card renders it as-is, deliberately no diff UI there — see
    what_changed.html). changes is an optional structured old/new diff,
    stored on the side for callers that want it later (e.g. an audit view);
    must already be JSON-safe (dates as ISO strings, etc.) before calling."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ActivityLog
    try:
        entry = ActivityLog(
            user_id=user.id if user else None,
            action=action,
            description=description,
            entity_type=entity_type,
            entity_name=entity_name,
            entity_id=entity_id,
            changes=changes
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        import traceback
        traceback.print_exc()