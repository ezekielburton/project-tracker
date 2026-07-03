"""
Achievement checker service. Single entry point: check_achievements().

Call this AFTER committing whatever action just happened (project
submission, login, a comment, etc.) — same ordering rule CLAUDE.md
documents for create_notification(): commit your own state changes
first, then call this, since it does its own commit(s) internally.

This file lives as a flat top-level module (app/achievements.py), not
app/utils/achievements.py as originally sketched — app/utils.py is
currently a single file, not a package, and converting it just to fit
this one new function would be unnecessary churn. This matches how
app/notifications.py and app/nas.py already sit directly under app/.
"""
from datetime import datetime


def check_achievements(user, event_type, metadata=None):
    """
    Advances progress on every Achievement whose trigger_event matches
    event_type, for the given user. If progress reaches an achievement's
    threshold, marks it earned, notifies the user, and logs an activity
    entry.

    metadata is accepted but not used by any achievement logic yet — a
    placeholder for future achievements needing more than a simple "+1
    per event" rule (e.g. "submit with zero revisions"). Kept now so call
    sites already pass it and won't need to change when that day comes.

    Never raises — any error here is caught, rolled back, and logged
    rather than propagated, the same defensive pattern log_activity()
    already uses in app/utils.py. This is called from the tail end of
    many unrelated, already-critical routes (submission, approval,
    login...) — a bug in achievement logic must never break any of those.
    """
    from app import db
    from app.models import Achievement, UserAchievement
    from app.notifications import create_notification
    from app.utils import log_activity

    try:
        # Only achievements actually wired to this event. Most calls will
        # match zero or one achievement, but nothing stops an admin from
        # defining several achievements on the same trigger_event (e.g. a
        # "10 submissions" and a "50 submissions" achievement both
        # listening for 'project_submitted').
        matching_achievements = Achievement.query.filter_by(trigger_event=event_type).all()

        for achievement in matching_achievements:
            # Upsert: find this user's progress row for this achievement,
            # or create one starting at 0 the first time they trigger it.
            user_achievement = UserAchievement.query.filter_by(
                user_id=user.id, achievement_id=achievement.id
            ).first()

            if user_achievement is None:
                user_achievement = UserAchievement(
                    user_id=user.id, achievement_id=achievement.id, progress=0
                )
                db.session.add(user_achievement)

            # Already earned — don't keep incrementing progress past the
            # threshold or re-fire the notification a second time. Also
            # protects against an achievement whose threshold got lowered
            # by an admin after some users already earned it.
            if user_achievement.earned_at is not None:
                continue

            user_achievement.progress += 1

            newly_earned = user_achievement.progress >= achievement.threshold
            if newly_earned:
                user_achievement.earned_at = datetime.utcnow()

            # Commit the progress/earned state before notifying — same
            # ordering rule CLAUDE.md documents for every other
            # create_notification() call site in this app.
            db.session.commit()

            if newly_earned:
                log_activity(
                    'achievement_earned',
                    f'{user.name} earned the achievement "{achievement.name}"',
                    user=user, entity_type='achievement',
                    entity_name=achievement.name, entity_id=achievement.id
                )
                create_notification(
                    recipient=user,
                    message=f'You earned: {achievement.name}',
                    notification_type='achievement_earned',
                    triggered_by=None  # system-earned, not caused by another user's action
                )
    except Exception:
        db.session.rollback()
        import traceback
        traceback.print_exc()
