# Business-hours totals derived from *StatusLog history (one row per status
# an entity was in: status, started_at, ended_at; ended_at is None for the
# current status). No DB writes; recomputed on every read.
#
# Rules:
#   - Business hours only: Mon-Fri, 10AM-6PM Dubai time.
#   - Weekend hours count only if a status change happened that weekend.
#   - Totals are kept per status as well as overall.

from datetime import datetime, timedelta, timezone, time

from app.modules.core.shared.models import Project

# Fixed UTC+4: ZoneInfo's tzdata is not reliably present on the Windows host.
DUBAI_TZ = timezone(timedelta(hours=4))

BUSINESS_START_HOUR = 10
BUSINESS_END_HOUR = 18

# Statuses left out of the "overall" total; every other status counts.
EXCLUDED_FROM_OVERALL = {'in_queue', 'submitted_to_client', 'internal_revision', 'on_hold'}


def _to_dubai(dt_utc):
    """Naive UTC datetime -> aware Dubai-local datetime."""
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(DUBAI_TZ)


def _business_window(day_date):
    """(start, end) aware Dubai datetimes for the 10AM-6PM window on the
    given date (a plain `date`, already Dubai-local)."""
    start = datetime.combine(day_date, time(BUSINESS_START_HOUR, 0), tzinfo=DUBAI_TZ)
    end = datetime.combine(day_date, time(BUSINESS_END_HOUR, 0), tzinfo=DUBAI_TZ)
    return start, end


def _confirmed_weekend_saturdays(rows):
    """Saturdays (as `date`) of weekends where any row's started_at falls
    on Sat/Sun, Dubai-local. One transition confirms both days, for every
    segment that overlaps that weekend."""
    confirmed = set()
    for r in rows:
        local = _to_dubai(r.started_at)
        weekday = local.weekday()  # Monday=0 ... Sunday=6
        if weekday == 5:  # Saturday
            confirmed.add(local.date())
        elif weekday == 6:  # Sunday
            confirmed.add(local.date() - timedelta(days=1))  # that weekend's Saturday
    return confirmed


def _overlap_hours(seg_start, seg_end, window_start, window_end):
    lo = max(seg_start, window_start)
    hi = min(seg_end, window_end)
    if hi <= lo:
        return 0.0
    return (hi - lo).total_seconds() / 3600.0


def _segment_business_hours(started_at_utc, ended_at_utc, confirmed_weekends):
    """Business hours between two naive-UTC datetimes. Sat/Sun count only
    when that weekend's Saturday is in `confirmed_weekends`."""
    start_local = _to_dubai(started_at_utc)
    end_local = _to_dubai(ended_at_utc)
    if end_local <= start_local:
        return 0.0

    total = 0.0
    day = start_local.date()
    last_day = end_local.date()
    while day <= last_day:
        weekday = day.weekday()  # Monday=0 ... Sunday=6
        if weekday in (5, 6):  # Saturday or Sunday
            saturday = day if weekday == 5 else day - timedelta(days=1)
            if saturday not in confirmed_weekends:
                day += timedelta(days=1)
                continue
        win_start, win_end = _business_window(day)
        total += _overlap_hours(start_local, end_local, win_start, win_end)
        day += timedelta(days=1)
    return total


def compute_status_hours(rows, now_utc=None):
    """Returns {'overall': hours, 'by_status': {status: hours}} for one
    entity's status-log rows (any order). An open row counts up to now_utc
    (default utcnow())."""
    if now_utc is None:
        now_utc = datetime.utcnow()

    rows = sorted(rows, key=lambda r: r.started_at)
    confirmed_weekends = _confirmed_weekend_saturdays(rows)

    by_status = {}
    overall = 0.0
    for r in rows:
        end = r.ended_at or now_utc
        hours = _segment_business_hours(r.started_at, end, confirmed_weekends)
        by_status[r.status] = by_status.get(r.status, 0.0) + hours
        if r.status not in EXCLUDED_FROM_OVERALL:
            overall += hours

    return {
        'overall': round(overall, 1),
        'by_status': {k: round(v, 1) for k, v in by_status.items()},
    }


def compute_project_hours(project, now_utc=None):
    """Hours from the project's status-log history (the status_logs backref)."""
    return compute_status_hours(project.status_logs, now_utc=now_utc)


def compute_deliverable_hours(deliverable, now_utc=None):
    """Hours from the deliverable's status-log history (the status_logs backref)."""
    return compute_status_hours(deliverable.status_logs, now_utc=now_utc)


def build_time_tracking_rows():
    """One row per non-draft project with its hours breakdown and each
    deliverable's. Per-customer status logs are not included.
    No access check: the /time-tracking page and the dashboard's Average
    Time card gate on view_time_reports before calling."""
    projects = Project.query.filter(Project.project_status != 'draft').order_by(Project.name).all()

    rows = []
    for p in projects:
        deliverables = []
        for d in p.project_deliverables:
            d_hours = compute_deliverable_hours(d)
            deliverables.append({
                'id': d.id,
                'name': d.name,
                'overall': d_hours['overall'],
                'by_status': d_hours['by_status'],
            })

        p_hours = compute_project_hours(p)
        rows.append({
            'id': p.id,
            'name': p.name,
            'overall': p_hours['overall'],
            'by_status': p_hours['by_status'],
            'deliverables': deliverables,
        })

    return rows
