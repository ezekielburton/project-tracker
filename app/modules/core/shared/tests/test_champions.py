"""Weekly OVP champion helpers and the Friction Log write gate (a capability
OR a current champion badge in any department).
"""
from datetime import timedelta

from app.modules.core.shared.lib.champions import (
    CHAMPION_DEPARTMENTS,
    can_write_friction,
    champion_for_week,
    current_champions,
    is_champion,
    week_start_for,
)
from app.modules.core.shared.models import OvpChampion, User


def _user(db_session, tag, role='designer'):
    user = User(name=f'Champion {tag}', email=f'champion-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _assign(db_session, user, department, week_start, set_by=None):
    row = OvpChampion(user_id=user.id, department=department, week_start=week_start,
                      set_by_id=set_by.id if set_by else None)
    db_session.add(row)
    db_session.flush()
    return row


def test_week_start_is_the_monday_of_that_week():
    monday = week_start_for()
    assert monday.weekday() == 0
    assert week_start_for(monday + timedelta(days=4)) == monday


def test_the_department_list_has_unique_keys_and_labels():
    keys = [key for key, _ in CHAMPION_DEPARTMENTS]
    labels = [label for _, label in CHAMPION_DEPARTMENTS]
    assert len(keys) == len(set(keys))
    assert len(labels) == len(set(labels))


def test_no_assignment_means_no_champions(app, db_session):
    assert current_champions() == {}


def test_each_department_holds_its_own_champion(app, db_session):
    cs = _user(db_session, 'cs-holder')
    design = _user(db_session, 'design-holder')
    _assign(db_session, cs, 'client_servicing', week_start_for())
    _assign(db_session, design, 'design', week_start_for())

    holders = current_champions()
    assert holders['client_servicing'].id == cs.id
    assert holders['design'].id == design.id
    assert 'production' not in holders


def test_a_department_falls_back_to_its_own_most_recent(app, db_session):
    """A missed rotation falls back to that department's own latest holder."""
    older = _user(db_session, 'older')
    recent = _user(db_session, 'recent')
    other = _user(db_session, 'other-dept')
    _assign(db_session, older, 'production', week_start_for() - timedelta(weeks=3))
    _assign(db_session, recent, 'production', week_start_for() - timedelta(weeks=1))
    _assign(db_session, other, 'finance', week_start_for())

    assert current_champions()['production'].id == recent.id
    assert current_champions()['finance'].id == other.id


def test_champion_for_week_reads_the_history_without_a_fallback(app, db_session):
    user = _user(db_session, 'history')
    last_week = week_start_for() - timedelta(weeks=1)
    _assign(db_session, user, 'logistics', last_week)

    assert champion_for_week(last_week)['logistics'].id == user.id
    assert champion_for_week(week_start_for()) == {}


def test_is_champion_is_true_for_any_department_held(app, db_session):
    holder = _user(db_session, 'holder')
    other = _user(db_session, 'not-holder')
    _assign(db_session, holder, 'logistics', week_start_for())

    assert is_champion(holder)
    assert not is_champion(other)


def test_a_champion_of_any_department_may_write_friction(app, db_session):
    designer = _user(db_session, 'gate-designer')
    _assign(db_session, designer, 'design', week_start_for())
    assert can_write_friction(designer)


def test_management_and_admin_may_write_friction(app, db_session):
    assert can_write_friction(_user(db_session, 'gate-management', 'management'))
    assert can_write_friction(_user(db_session, 'gate-admin', 'admin'))


def test_a_plain_designer_may_not_write_friction(app, db_session):
    assert not can_write_friction(_user(db_session, 'gate-plain'))
