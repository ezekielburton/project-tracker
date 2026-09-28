"""Achievement checker; entry point check_achievements().

Call it AFTER committing the triggering action: it commits internally. A
failure rolls back only its own SAVEPOINT, never the caller's pending work.
"""
from datetime import datetime

from flask import current_app


def check_achievements(user, event_type):
    """+1 progress on each achievement whose trigger_event is event_type; at
    the threshold, mark it earned, notify the user and log it. Never raises:
    it runs at the end of critical routes, so errors are logged."""
    from app.modules.core.shared.extensions import db
    from app.modules.core.shared.models import Achievement, UserAchievement
    from app.modules.core.shared.services.notifications import create_notification
    from app.modules.core.shared.lib.utils import log_activity

    progressed = False
    newly_earned = []
    try:
        # SAVEPOINT: an error rolls back only this work, never the caller's.
        with db.session.begin_nested():
            # Several achievements can share a trigger_event (e.g. 10 and 50 submissions).
            matching_achievements = Achievement.query.filter_by(trigger_event=event_type).all()

            for achievement in matching_achievements:
                # Progress row is created on first trigger.
                user_achievement = UserAchievement.query.filter_by(
                    user_id=user.id, achievement_id=achievement.id
                ).first()

                if user_achievement is None:
                    user_achievement = UserAchievement(
                        user_id=user.id, achievement_id=achievement.id, progress=0
                    )
                    db.session.add(user_achievement)

                # Already earned: stop counting and never re-notify (also covers
                # a threshold lowered after users earned it).
                if user_achievement.earned_at is not None:
                    continue

                user_achievement.progress += 1
                progressed = True

                if user_achievement.progress >= achievement.threshold:
                    user_achievement.earned_at = datetime.utcnow()
                    newly_earned.append(achievement)
    except Exception:
        current_app.logger.exception(f'Achievement check failed for user {user.id} ({event_type})')
        return

    if not progressed:
        return

    try:
        # Commit progress before notifying.
        db.session.commit()
        for achievement in newly_earned:
            log_activity(
                'achievement_earned',
                f'{user.name} earned the achievement "{achievement.name}"',
                user=user, entity_type='achievement',
                entity_name=achievement.name, entity_id=achievement.id
            )
            from flask import url_for
            create_notification(
                recipient=user,
                message=f'You earned: {achievement.name}',
                notification_type='achievement_earned',
                triggered_by=None,  # system-earned, not caused by another user's action
                link=url_for('profile.view', user_id=user.id)
            )
    except Exception:
        # Past the SAVEPOINT the caller's work is committed with ours (or its
        # commit already failed), so a full rollback loses nothing more.
        db.session.rollback()
        current_app.logger.exception(f'Achievement notification failed for user {user.id} ({event_type})')
