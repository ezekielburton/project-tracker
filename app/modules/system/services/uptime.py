"""What the admin Uptime page shows. The heartbeat checks /healthz every
minute; a gap longer than GAP between beats, a failed beat, or a latest beat
older than GAP is downtime. Downtime that starts within PLANNED_WINDOW of a
deploy reads as a planned restart."""
from datetime import date, datetime, timedelta

from sqlalchemy import func, text

from app.modules.core.shared.extensions import db
from app.modules.system.lib import fmt
from app.modules.system.models import DeployRun, Heartbeat, SystemIncident

WINDOW = timedelta(days=30)
GAP = timedelta(seconds=150)
BEAT = timedelta(minutes=1)
PLANNED_WINDOW = timedelta(minutes=15)
DEPLOYS_SHOWN = 8
INCIDENTS_SHOWN = 10
TITLE_LENGTH = 120

_GAPS = text(
    'SELECT prev, ts FROM (SELECT ts, lag(ts) OVER (ORDER BY ts) AS prev FROM heartbeats '
    'WHERE ts >= :since) beats WHERE ts - prev > :gap ORDER BY ts')


def _merge(stretches):
    merged = []
    for start, end in sorted(stretches):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def outages(now=None, since=None):
    """[{start, end, minutes, planned, ongoing}] oldest first, from the heartbeats since `since`."""
    now = now or datetime.utcnow()
    since = since or now - WINDOW
    stretches = [(prev + BEAT, ts) for prev, ts in db.session.execute(_GAPS, {'since': since, 'gap': GAP})]
    stretches += [(ts - BEAT, ts) for (ts,) in db.session.query(Heartbeat.ts)
                  .filter(Heartbeat.ts >= since, Heartbeat.ok.is_(False))]
    last = db.session.query(func.max(Heartbeat.ts)).scalar()
    ongoing_from = last + BEAT if last is not None and now - last > GAP else None
    if ongoing_from is not None:
        stretches.append((ongoing_from, now))
    deploys = [row.ran_at for row in DeployRun.query.filter(DeployRun.ran_at >= since - PLANNED_WINDOW)]
    result = []
    for start, end in _merge(stretches):
        result.append({'start': start, 'end': end,
                       'minutes': max(round((end - start).total_seconds() / 60), 1),
                       'planned': any(abs(start - ran) <= PLANNED_WINDOW for ran in deploys),
                       'ongoing': ongoing_from is not None and end == now})
    return result


def _watched_from(now):
    """When the heartbeat record starts inside the window, or None before the first beat."""
    first = db.session.query(func.min(Heartbeat.ts)).scalar()
    return None if first is None else max(first, now - WINDOW)


def _down_minutes(found, start, end):
    total = 0.0
    for outage in found:
        overlap = (min(outage['end'], end) - max(outage['start'], start)).total_seconds()
        total += max(overlap, 0) / 60
    return total


def summary(snapshot, now=None):
    """Uptime % and minutes down (30 days), unplanned outages, the last restart and the last deploy."""
    now = now or datetime.utcnow()
    watched = _watched_from(now)
    found = outages(now) if watched else []
    down = _down_minutes(found, watched, now) if watched else 0
    span = (now - watched).total_seconds() / 60 if watched else 0
    workers = snapshot.get('workers') or {}
    started = datetime.utcfromtimestamp(workers['started_at']) if workers.get('started_at') else None
    deploy = DeployRun.query.order_by(DeployRun.ran_at.desc()).first()
    return {
        'pct': round(100 * (1 - down / span), 2) if span else None,
        'down_minutes': round(down),
        'incidents': sum(1 for outage in found if not outage['planned']),
        'ongoing': any(outage['ongoing'] for outage in found),
        'since_restart': None if started is None else {
            'days': (now - started).days, 'hours': (now - started).seconds // 3600,
            'date': f"{fmt.local(started).day} {fmt.local(started):%b}"},
        'deploy': None if deploy is None else {
            'tag': deploy.tag or (deploy.commit_sha or '')[:7] or 'deploy', 'ago': fmt.ago(deploy.ran_at, now),
            'migrations': deploy.migrations_applied, 'ok': deploy.ok},
    }


def days(now=None):
    """30 Dubai days, oldest first: {day, state, down}. State is grey before the
    first heartbeat, red with unplanned downtime, amber with only planned, else green."""
    now = now or datetime.utcnow()
    watched = _watched_from(now)
    found = outages(now) if watched else []
    offset = fmt.DUBAI.utcoffset(None)
    today = (now + offset).replace(hour=0, minute=0, second=0, microsecond=0)
    result = []
    for back in range(29, -1, -1):
        local_start = today - timedelta(days=back)
        start, end = local_start - offset, min(local_start - offset + timedelta(days=1), now)
        if watched is None or end <= watched:
            result.append({'day': local_start.date(), 'state': 'grey', 'down': 0})
            continue
        unplanned = _down_minutes([o for o in found if not o['planned']], start, end)
        planned = _down_minutes([o for o in found if o['planned']], start, end)
        state = 'red' if unplanned >= 1 else 'amber' if planned >= 1 else 'green'
        result.append({'day': local_start.date(), 'state': state, 'down': round(unplanned + planned)})
    return result


def deploys(now=None, limit=DEPLOYS_SHOWN):
    """[{tag, when, migrations, duration, ok}] newest first."""
    now = now or datetime.utcnow()
    rows = DeployRun.query.order_by(DeployRun.ran_at.desc()).limit(limit).all()
    return [{'tag': row.tag or (row.commit_sha or '')[:7], 'when': fmt.day_time(row.ran_at, now),
             'migrations': row.migrations_applied, 'duration': fmt.ms(row.duration_ms), 'ok': row.ok}
            for row in rows]


def incidents(limit=INCIDENTS_SHOWN):
    """[{title, minutes, note, date}] newest first."""
    rows = (SystemIncident.query.order_by(SystemIncident.happened_on.desc(), SystemIncident.created_at.desc())
            .limit(limit).all())
    return [{'title': row.title or 'Incident', 'minutes': row.minutes, 'note': row.note,
             'date': f'{row.happened_on.day} {row.happened_on:%b}'} for row in rows]


class IncidentError(ValueError):
    """What is wrong with an incident the admin tried to add, in words for the form."""


def add_incident(title, minutes, note, happened_on, user_id, today=None):
    """Save an incident note. Title required; minutes a whole number from 0; the
    date not in the future. Raises IncidentError; the caller commits."""
    title = (title or '').strip()
    if not title:
        raise IncidentError('Add a title')
    if len(title) > TITLE_LENGTH:
        raise IncidentError(f'Keep the title under {TITLE_LENGTH} characters')
    if minutes in (None, ''):
        minutes = None
    else:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            raise IncidentError('Minutes must be a whole number') from None
        if minutes < 0:
            raise IncidentError('Minutes must be a whole number')
    today = today or fmt.local(datetime.utcnow()).date()
    if happened_on in (None, ''):
        happened_on = today
    elif not isinstance(happened_on, date):
        try:
            happened_on = date.fromisoformat(happened_on)
        except (TypeError, ValueError):
            raise IncidentError('Pick a date') from None
    if happened_on > today:
        raise IncidentError('The date can’t be in the future')
    incident = SystemIncident(title=title, minutes=minutes, note=(note or '').strip() or None,
                              happened_on=happened_on, created_by_id=user_id)
    db.session.add(incident)
    return incident
