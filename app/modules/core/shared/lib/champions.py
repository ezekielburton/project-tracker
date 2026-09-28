"""Weekly OVP champions: who holds each department's badge, and the Friction
Log write gate. The badge rotates weekly and is separate from User.role.
"""
from datetime import date, timedelta

from sqlalchemy.orm import joinedload

from app.modules.core.shared.lib.capabilities import can
from app.modules.core.shared.models import OvpChampion

# Departments that rotate a champion, in admin-panel order. Management and
# admin already hold write_friction_log, so they get no badge.
CHAMPION_DEPARTMENTS = [
    ('client_servicing', 'Client Servicing'),
    ('design', 'Design'),
    ('production', 'Production'),
    ('logistics', 'Logistics'),
    ('finance', 'Finance'),
]

DEPARTMENT_LABELS = dict(CHAMPION_DEPARTMENTS)


# A champion who was not replaced keeps the badge this many weeks, so one
# missed rotation does not leave a department empty; older badges lapse.
CHAMPION_CARRY_OVER_WEEKS = 2


def week_start_for(day=None):
    """The Monday of the week `day` falls in; today's Monday when omitted."""
    day = day or date.today()
    return day - timedelta(days=day.weekday())


def _carry_over_floor(week_start):
    """The oldest assignment still considered current for that week."""
    return week_start - timedelta(weeks=CHAMPION_CARRY_OVER_WEEKS)


def champion_for_week(week_start):
    """{department: User} for assignments made in that exact week; no
    carry-over."""
    rows = (OvpChampion.query
            .filter_by(week_start=week_start)
            .options(joinedload(OvpChampion.user))
            .all())
    return {r.department: r.user for r in rows}


def current_champions():
    """{department: User} for every live champion, in one query bounded to the
    carry-over window (it runs on every Friction Log access check). Departments
    with no live assignment are absent."""
    this_week = week_start_for()
    rows = (OvpChampion.query
            .filter(OvpChampion.week_start <= this_week,
                    OvpChampion.week_start >= _carry_over_floor(this_week))
            .options(joinedload(OvpChampion.user))
            .order_by(OvpChampion.week_start.desc())
            .all())
    found = {}
    for row in rows:
        if row.department in DEPARTMENT_LABELS and row.department not in found:
            found[row.department] = row.user
    return found


def is_champion(user):
    """True if this person holds any department's badge right now."""
    user_id = getattr(user, 'id', None)
    if user_id is None:
        return False
    return any(holder.id == user_id for holder in current_champions().values())


def can_write_friction(user):
    """Friction Log write access — any current champion, plus whoever the map grants."""
    return is_champion(user) or can('write_friction_log', user)
