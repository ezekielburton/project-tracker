"""check_achievements(): a failure inside the achievement work rolls back only
its own SAVEPOINT, so the caller's uncommitted changes survive."""
from app.modules.core.shared.models import Achievement, AchievementCategory, User, UserAchievement
from app.modules.core.shared.services import achievements as achievements_service


def _user(db_session, tag):
    user = User(name=f'Achiever {tag}', email=f'achiever-{tag}@example.com', role='designer')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _achievement(db_session, event, threshold=1):
    category = AchievementCategory(name='Test category')
    db_session.add(category)
    db_session.flush()
    achievement = Achievement(category_id=category.id, name=f'Test {event}',
                              trigger_event=event, threshold=threshold)
    db_session.add(achievement)
    db_session.flush()
    return achievement


class _BrokenClock:
    @staticmethod
    def utcnow():
        raise RuntimeError('clock exploded')


def test_an_achievement_error_keeps_the_callers_pending_change(app, db_session, monkeypatch):
    user = _user(db_session, 'savepoint')
    achievement = _achievement(db_session, 'savepoint_event')
    db_session.commit()

    user.name = 'Renamed by the caller'  # pending, not flushed
    monkeypatch.setattr(achievements_service, 'datetime', _BrokenClock)

    achievements_service.check_achievements(user, 'savepoint_event')

    assert user.name == 'Renamed by the caller'
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(User, user.id).name == 'Renamed by the caller'
    # The achievement work itself was undone.
    assert UserAchievement.query.filter_by(user_id=user.id, achievement_id=achievement.id).first() is None


def test_progress_is_recorded_and_earned_at_the_threshold(app, db_session):
    user = _user(db_session, 'earn')
    achievement = _achievement(db_session, 'earn_event', threshold=2)
    db_session.commit()

    achievements_service.check_achievements(user, 'earn_event')
    row = UserAchievement.query.filter_by(user_id=user.id, achievement_id=achievement.id).one()
    assert row.progress == 1 and row.earned_at is None

    with app.test_request_context():  # the earned notification builds a url_for link
        achievements_service.check_achievements(user, 'earn_event')
    db_session.refresh(row)
    assert row.progress == 2 and row.earned_at is not None
