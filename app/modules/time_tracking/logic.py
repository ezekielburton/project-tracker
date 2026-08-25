# Business-hours computation for the time-tracking feature. Pure functions:
# no Flask/DB writes, they derive hour totals from the *StatusLog history
# (one row per status an entity was ever in: status, started_at, ended_at;
# ended_at is None while it is the entity's current status).
#
# The rules the numbers follow:
#   - Business hours only: Mon-Fri, 10AM-6PM Dubai time.
#   - Weekend hours (Sat/Sun) are discarded unless a status change actually
#     happened that weekend (a transition is taken as evidence of real work).
#   - Broken down per status, not just one aggregate, feeding the
#     project+deliverable drill-down page.
#
# Everything is recomputed from the status-log history on every read, so the
# numbers are always derivable from history and there is no separate counter
# to keep in sync. This file is the one place to change the business-hours
# window, the weekend rule, or the excluded-status set.

from datetime import datetime, timedelta, timezone, time

from app.modules.core.shared.models import Project

# Fixed UTC+4 offset for Dubai. A fixed offset rather than ZoneInfo, whose
# tzdata is not reliably present on the app's Windows host.
DUBAI_TZ = timezone(timedelta(hours=4))

BUSINESS_START_HOUR = 10
BUSINESS_END_HOUR = 18

# Statuses that do NOT count toward the "overall" active-time total.
# Framed as an exclusion set: every other status (including 'approved')
# counts as active time by default.
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
    """
    A 'confirmed' weekend is one where at least one status transition (a
    log row's started_at — the moment the PREVIOUS status ended and this
    one began) fell on a Saturday or Sunday, Dubai-local. Returns a set of
    `date` objects, each the Saturday of a confirmed weekend.

    Per Ezekiel: "silently track saturday and sunday but discard those
    hours on the following Monday if the status didn't change. If the
    status changes on the weekend, those hours get added ... because that
    indicates it was worked on." A transition ANYWHERE in a weekend
    confirms the WHOLE weekend (both days) — the segment ending at that
    transition and the segment starting from it both get credited for
    their weekend portions. That's what "discard on Monday if nothing
    changed" implies: the check is per-weekend, not per-minute.
    """
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
    """
    Business hours (10AM-6PM Dubai) between two naive-UTC datetimes, for
    ONE status segment — Mon-Fri always counted, Sat/Sun only counted if
    that weekend (identified by its Saturday's date) is in
    `confirmed_weekends`.
    """
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
    """
    Given a list of *StatusLog rows for ONE entity (project or
    deliverable), sorted or not (this sorts them), returns:

        {
          'overall': <business hours across all non-excluded statuses>,
          'by_status': {status: business_hours, ...},  # every status seen
        }

    An open row (ended_at is None — the entity's CURRENT status) is
    treated as ending "now" (now_utc, defaulting to datetime.utcnow()) so
    time in the current status counts up to the moment of viewing, not
    just up to the last completed transition.
    """
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
    """
    One row per non-draft project, each with its own overall and per-status
    business-hours breakdown, plus the same breakdown for each of its
    (standard-brief) deliverables. Company-wide, not scoped to one CS lead.

    C&CM per-customer status history (ProjectCustomerStatusLog) is not
    included — the breakdown is per project and per standard-brief deliverable.

    No access check here — that is the caller's job. This feeds both the
    /time-tracking page and the dashboard's Average Time card, each of which
    gates on admin/management before calling.
    """
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
