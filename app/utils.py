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
    from app.models import User
    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        return User.query.get(emulating_id)
    return current_user

def work_hours_between(start, end):
    """Elapsed hours between two datetimes, as a plain wall-clock duration
    (added 13 Jul 2026, re-wiring the project time-tracking feature — see
    record_project_status() in app/status_tracking.py, the only caller).

    This is a straightforward (end - start) in hours, NOT a "business
    hours" calculation that excludes nights/weekends/holidays — there was
    no prior working implementation to match (the old, never-registered
    app/routes/projects_old.py referenced a function of this name but
    never defined it), and nothing in the codebase specifies working-hours
    semantics, so the simplest honest interpretation was used. If Ezekiel
    wants project timers to only count business hours, this is the one
    place that needs to change.
    """
    return (end - start).total_seconds() / 3600.0


def log_activity(action, description, user=None, entity_type=None, entity_name=None, entity_id=None):
    from app import db
    from app.models import ActivityLog
    try:
        entry = ActivityLog(
            user_id=user.id if user else None,
            action=action,
            description=description,
            entity_type=entity_type,
            entity_name=entity_name,
            entity_id=entity_id
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        import traceback
        traceback.print_exc()