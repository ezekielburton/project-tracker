"""What the admin Usage page shows, from request metrics. Admins and the
USAGE_EXCLUDED_EMAILS accounts are left out of every count; an action is a
saved change (lib/actions)."""
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import func

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.org import DEPARTMENTS, seniority_label
from app.modules.core.shared.models import User
from app.modules.system.lib import fmt, modules
from app.modules.system.models import RequestMetric
from app.modules.system.services import health

DAYS_SHOWN = 14
MODULE_WINDOW = timedelta(days=30)
HOUR_WINDOW = timedelta(days=30)
MODULES_SHOWN = 8
LOGINS_SHOWN = 6
EMULATIONS_SHOWN = 6
EMULATION_WINDOW = timedelta(days=30)
# Requests further apart than this start a new emulation session.
EMULATION_GAP = timedelta(minutes=30)

_LOCAL = fmt.DUBAI.utcoffset(None)


def _action_count(since, until=None):
    query = RequestMetric.query.filter(RequestMetric.ts >= since)
    if until is not None:
        query = query.filter(RequestMetric.ts < until)
    return health.actions(health.counted(query)).count()


def _people_between(since, until):
    return (health.counted(db.session.query(func.count(func.distinct(RequestMetric.user_id)))
                           .filter(RequestMetric.ts >= since, RequestMetric.ts < until)).scalar() or 0)


def by_module(now=None, limit=MODULES_SHOWN):
    """[{module, actions, share}] over 30 days, busiest first; share is a % of all actions."""
    now = now or datetime.utcnow()
    module = modules.module_column(RequestMetric.blueprint)
    inner = (health.actions(health.counted(db.session.query(module.label('module'))
                                           .filter(RequestMetric.ts >= now - MODULE_WINDOW)))
             .subquery())
    rows = (db.session.query(inner.c.module, func.count()).group_by(inner.c.module)
            .order_by(func.count().desc(), inner.c.module).all())
    total = sum(count for _, count in rows)
    return [{'module': name, 'actions': count, 'share': round(100 * count / total)}
            for name, count in rows[:limit]]


def tiles(now=None):
    """Active now (of all staff), actions today against the 30-day daily
    average, people this week against last week, and the top module."""
    now = now or datetime.utcnow()
    midnight = health.dubai_midnight(now)
    excluded = health.excluded_user_ids()
    staff = User.query.filter(User.is_active.is_(True))
    if excluded:
        staff = staff.filter(User.id.notin_(excluded))
    week_start = midnight - timedelta(days=fmt.local(now).weekday())
    modules_30d = by_module(now, limit=1)
    return {
        'active_now': health.people_since(now - health.ACTIVE_NOW),
        'staff': staff.count(),
        'actions_today': _action_count(midnight),
        'daily_average': round(_action_count(midnight - timedelta(days=30), midnight) / 30),
        'people_week': health.people_since(week_start),
        'people_last_week': _people_between(week_start - timedelta(days=7), week_start),
        'top_module': modules_30d[0] if modules_30d else None,
    }


def per_day(now=None, days=DAYS_SHOWN):
    """[{day, actions}] for each Dubai day, oldest first, today last."""
    now = now or datetime.utcnow()
    midnight = health.dubai_midnight(now)
    first = midnight - timedelta(days=days - 1)
    day = func.date_trunc('day', RequestMetric.ts + _LOCAL)
    counts = dict(health.actions(health.counted(db.session.query(day, func.count())
                                                .filter(RequestMetric.ts >= first)))
                  .group_by(day).all())
    result = []
    for index in range(days):
        local_day = (first + _LOCAL + timedelta(days=index)).replace(hour=0, minute=0, second=0, microsecond=0)
        result.append({'day': local_day.date(), 'actions': counts.get(local_day, 0)})
    return result


def by_hour(now=None):
    """Actions in each Dubai hour of the day over 30 days, as a list of 24."""
    now = now or datetime.utcnow()
    hour = func.extract('hour', RequestMetric.ts + _LOCAL)
    counts = dict(health.actions(health.counted(db.session.query(hour, func.count())
                                                .filter(RequestMetric.ts >= now - HOUR_WINDOW)))
                  .group_by(hour).all())
    counts = {int(key): value for key, value in counts.items()}
    return [counts.get(index, 0) for index in range(24)]


def _who(user):
    """'2D', 'Client Servicing', 'Management': the team, else the department, else the level."""
    if user.team:
        return user.team
    if user.department:
        return DEPARTMENTS.get(user.department, user.department)
    return seniority_label(user)


def _login_rule():
    return next(rule.rule for rule in current_app.url_map.iter_rules() if rule.endpoint == 'auth.login')


def recent_logins(now=None, limit=LOGINS_SHOWN):
    """[{name, who, ago}] for the latest successful logins, newest first."""
    now = now or datetime.utcnow()
    rows = (health.counted(db.session.query(RequestMetric.ts, RequestMetric.user_id))
            .filter(RequestMetric.method == 'POST', RequestMetric.route == _login_rule(),
                    RequestMetric.status == 302)
            .order_by(RequestMetric.ts.desc()).limit(limit).all())
    users = {user.id: user for user in User.query.filter(User.id.in_({row.user_id for row in rows}))}
    result = []
    for ts, user_id in rows:
        user = users.get(user_id)
        if user is not None:
            result.append({'name': user.name, 'who': _who(user), 'ago': fmt.ago(ts, now)})
    return result


def sessions(rows, gap=EMULATION_GAP):
    """Group (ts, admin_id, emulated_id) rows into sessions: same pair, no gap
    longer than `gap`. Returns [(admin_id, emulated_id, start, end)], newest first."""
    found = []
    for ts, admin_id, emulated_id in sorted(rows, key=lambda row: (row[1], row[2], row[0])):
        last = found[-1] if found else None
        if last and last[0] == admin_id and last[1] == emulated_id and ts - last[3] <= gap:
            found[-1] = (admin_id, emulated_id, last[2], ts)
        else:
            found.append((admin_id, emulated_id, ts, ts))
    return sorted(found, key=lambda session: session[2], reverse=True)


def emulation_log(now=None, limit=EMULATIONS_SHOWN):
    """[{name, who, when, minutes}]: each time an admin viewed the app as
    someone in 30 days, newest first."""
    now = now or datetime.utcnow()
    rows = (db.session.query(RequestMetric.ts, RequestMetric.user_id, RequestMetric.emulating_id)
            .filter(RequestMetric.emulating_id.isnot(None), RequestMetric.ts >= now - EMULATION_WINDOW)
            .all())
    found = sessions(rows)[:limit]
    ids = {session[1] for session in found}
    users = {user.id: user for user in User.query.filter(User.id.in_(ids))} if ids else {}
    result = []
    for _, emulated_id, start, end in found:
        emulated = users.get(emulated_id)
        result.append({'name': emulated.name if emulated else 'a removed user',
                       'who': _who(emulated) if emulated else None,
                       'when': fmt.day_time(start, now),
                       'minutes': max(round((end - start).total_seconds() / 60), 1)})
    return result
