import re as _re
from html import unescape as _unescape
from datetime import datetime as _datetime

def slugify(text):
    """Convert a title to a URL-safe slug."""
    text = text.lower().strip()
    text = _re.sub(r'[^\w\s-]', '', text)
    text = _re.sub(r'[\s_]+', '-', text)
    return _re.sub(r'-+', '-', text).strip('-')

def file_type_label(ext):
    """Human label for a file extension ('an image', 'a PDF', ...), used in
    activity log sentences."""
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
    """Rich text to plain text for notifications and activity logs: drops tags,
    decodes entities, collapses whitespace."""
    if not html_text:
        return ''
    text = _re.sub(r'<[^>]+>', '', html_text)
    text = _unescape(text)
    return ' '.join(text.split())


def get_actor():
    """The user to record an action as: the emulated user while an admin
    emulates someone. Admin-only write routes use current_user instead.
    """
    from app.modules.core.shared.lib.capabilities import effective_user
    return effective_user()

# A user with no watermark row for a project counts as having seen it at this
# moment, so old history never shows as unread. The Projects table and the
# Chat tray both read it and must agree.
ACTIVITY_SEEN_ROLLOUT_CUTOFF = _datetime(2026, 8, 27, 6, 15, 0)

def mark_project_activity_seen(project, user, kind):
    """Set one of a user's per-project unread watermarks to now: kind 'update'
    (overlay opened) or 'chat' (chat drawer rendered). Upserts the
    ProjectActivitySeen row; best-effort, errors are printed and rolled back."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import ProjectActivitySeen

    column = {'update': 'last_seen_update_at', 'chat': 'last_seen_chat_at'}[kind]
    try:
        seen = ProjectActivitySeen.query.filter_by(project_id=project.id, user_id=user.id).first()
        if not seen:
            seen = ProjectActivitySeen(project_id=project.id, user_id=user.id)
            db.session.add(seen)
        setattr(seen, column, _datetime.utcnow())
        db.session.commit()
    except Exception:
        db.session.rollback()
        import traceback
        traceback.print_exc()


def log_activity(action, description, user=None, entity_type=None, entity_name=None, entity_id=None, changes=None):
    """Write an ActivityLog row. `description` is the sentence shown in the UI;
    `changes` is an optional old/new diff that must already be JSON-safe
    (dates as ISO strings). Best-effort: errors are printed and rolled back."""
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