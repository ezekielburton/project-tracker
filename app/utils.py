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