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