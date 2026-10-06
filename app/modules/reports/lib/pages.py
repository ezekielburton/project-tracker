"""What the Reports admin pages show. Routes only call these."""
from datetime import timedelta

from flask import url_for
from sqlalchemy import func

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.org import DEPARTMENTS, SENIORITY_LEVELS
from app.modules.core.shared.lib.timezone import local_midnight_utc, to_dubai
from app.modules.core.shared.models import User
from app.modules.reports.lib.people import DEPARTMENT_REPORTS, is_lead, people_for
from app.modules.reports.lib.period import MONTHLY, WEEKLY, Period
from app.modules.reports.lib.settings import recipients, switch_state
from app.modules.reports.models import ALL_REPORTS, PERIOD_KINDS, REPORTS, ReportRun

# Periods offered on Generate, newest first (this one included, for early sends).
OPTION_COUNT = 12
RECENT_COUNT = 6
HISTORY_LIMIT = 200

# Seniority levels suggested first as recipients of their department's report.
SUGGESTED_SENIORITY = ('head', 'manager')

RAIL = (
    ('generate', 'Generate', 'reports.generate_page', 'M14 3H6v18h12V7zM14 3v4h4M12 11v6M9 14h6'),
    ('history', 'History', 'reports.history_page', 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2'),
    ('recipients', 'Recipients', 'reports.recipients_page',
     'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8'),
)


def rail():
    return [{'key': key, 'label': label, 'url': url_for(endpoint), 'icon': icon}
            for key, label, endpoint, icon in RAIL]


def initials(name):
    parts = (name or '?').split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper()


def _stamp(dt_utc):
    """'Mon 5 Oct · 08:00' in Dubai time."""
    local = to_dubai(dt_utc)
    return f'{local:%a} {local.day} {local:%b} · {local:%H:%M}'


def _next_send(kind, today):
    """The next scheduled send day."""
    if kind == WEEKLY:
        return today + timedelta(days=(7 - today.weekday()) or 7)
    return Period.month_of(today).end + timedelta(days=1)


def run_row(run):
    """One ReportRun as the History and Recent tables show it."""
    period = run.period
    early = bool(run.made_by_id and run.sent_at and run.sent_at < period.scheduled_send_at())
    status = 'Sent early' if run.status == 'sent' and early else run.status.capitalize()
    return {
        'id': run.id, 'report': REPORTS.get(run.report, run.report), 'kind': run.period_kind.capitalize(),
        'period': period.short_label, 'made': _stamp(run.made_at),
        'how': run.made_by.name.split()[0] if run.made_by else 'Auto',
        'sent_to': [initials(u.name) for u in _users(run.sent_to)] if run.status == 'sent' else [],
        'status': status, 'status_key': 'early' if status == 'Sent early' else run.status,
        'error': run.error if run.status == 'failed' else None,
        'send_label': 'Resend' if run.sent_at else 'Send',
        'download_url': url_for('reports.download', run_id=run.id),
        'open_url': url_for('reports.download', run_id=run.id, view=1),
        'send_url': url_for('reports.api_send_run', run_id=run.id),
    }


def _users(ids):
    if not ids:
        return []
    return User.query.filter(User.id.in_(ids)).order_by(User.name).all()


def generate_view(today):
    options = {kind: [{'value': p.start.isoformat(), 'label': p.short_label,
                       'selected': p == Period.last_complete(kind, today)}
                      for p in _options(kind, today)] for kind in PERIOD_KINDS}
    reports = []
    for key, label in REPORTS.items():
        reports.append({'key': key, 'label': label, 'covers': _covers(key),
                        'recipients': len(recipients(key))})
    runs = ReportRun.query.order_by(ReportRun.made_at.desc()).limit(RECENT_COUNT).all()
    schedule = [{'kind': kind, 'label': kind.capitalize(), 'on': switch_state(ALL_REPORTS, kind),
                 'when': 'Mondays · 08:00' if kind == WEEKLY else '1st of the month · 08:00',
                 'next': _next_send(kind, today)} for kind in PERIOD_KINDS]
    return {'rail': rail(), 'active': 'generate', 'options': options, 'reports': reports,
            'recent': [run_row(r) for r in runs], 'schedule': schedule}


def _options(kind, today):
    period, out = Period.of(kind, today), []
    for _ in range(OPTION_COUNT):
        out.append(period)
        period = period.previous()
    return out


def _covers(report):
    if report not in DEPARTMENT_REPORTS:
        return 'all departments'
    people = people_for(report)
    leads = sum(1 for u in people if is_lead(u)) if report == 'design' else 0
    text = f'{len(people)} people'
    return f'{text} · {leads} leads' if leads else text


# History filters: query key -> (allowed values -> column test).
FILTERS = {
    'kind': PERIOD_KINDS,
    'report': tuple(REPORTS),
    'how': ('auto', 'manual'),
}


def history_view(args, today):
    active = {key: args.get(key) for key in FILTERS if args.get(key) in FILTERS[key]}
    query = ReportRun.query
    if 'kind' in active:
        query = query.filter(ReportRun.period_kind == active['kind'])
    if 'report' in active:
        query = query.filter(ReportRun.report == active['report'])
    if active.get('how') == 'auto':
        query = query.filter(ReportRun.made_by_id.is_(None))
    elif active.get('how') == 'manual':
        query = query.filter(ReportRun.made_by_id.isnot(None))
    runs = query.order_by(ReportRun.made_at.desc()).limit(HISTORY_LIMIT).all()
    return {'rail': rail(), 'active': 'history', 'rows': [run_row(r) for r in runs],
            'filters': active, 'chips': _chips(active), 'vitals': _vitals(today)}


def _chips(active):
    """Filter chips: (group, value, label, on). Clicking an on chip clears it."""
    groups = [('kind', [(k, k.capitalize()) for k in PERIOD_KINDS]),
              ('report', list(REPORTS.items())),
              ('how', [('auto', 'Auto'), ('manual', 'On demand')])]
    out = []
    for key, values in groups:
        group = []
        for value, label in values:
            on = active.get(key) == value
            params = {k: v for k, v in active.items() if k != key}
            if not on:
                params[key] = value
            group.append({'label': label, 'on': on, 'url': url_for('reports.history_page', **params)})
        out.append(group)
    return out


def _vitals(today):
    month_start = local_midnight_utc(today.replace(day=1))
    since_30 = local_midnight_utc(today - timedelta(days=30))
    base = ReportRun.query
    count, size = db.session.query(func.count(ReportRun.id), func.coalesce(func.sum(ReportRun.file_size), 0)).one()
    return {
        'sent': base.filter(ReportRun.status == 'sent', ReportRun.sent_at >= month_start).count(),
        'manual': base.filter(ReportRun.made_by_id.isnot(None), ReportRun.made_at >= month_start).count(),
        'failed': base.filter(ReportRun.status == 'failed', ReportRun.made_at >= since_30).count(),
        'stored': count, 'size_mb': round(size / 1_048_576, 1),
    }


def recipients_view():
    rows = []
    for key, label in REPORTS.items():
        rows.append({'key': key, 'label': label, 'covers': _covers(key),
                     'people': [{'id': u.id, 'name': u.name, 'initials': initials(u.name),
                                 'meta': _meta(u)} for u in recipients(key)],
                     'weekly': switch_state(key, WEEKLY), 'monthly': switch_state(key, MONTHLY),
                     'suggest': _suggested(key)})
    return {'rail': rail(), 'active': 'recipients', 'rows': rows, 'people': _picker()}


def _meta(user):
    if user.is_admin:
        return 'Admin'
    if user.seniority and user.seniority != 'none':
        return SENIORITY_LEVELS.get(user.seniority, '')
    return DEPARTMENTS.get(user.department, '')


def _picker():
    """Everyone who can be added, for the Add popover."""
    users = User.query.filter(User.is_active.is_(True)).order_by(User.name).all()
    return [{'id': u.id, 'name': u.name, 'initials': initials(u.name), 'meta': _meta(u),
             'department': u.department, 'seniority': u.seniority} for u in users]


def _suggested(report):
    """Heads and managers of the report's department, shown first in Add."""
    if report not in DEPARTMENT_REPORTS:
        return [u.id for u in User.query.filter(User.is_active.is_(True), User.seniority == 'management')]
    return [u.id for u in User.query.filter(User.is_active.is_(True), User.department == report,
                                            User.seniority.in_(SUGGESTED_SENIORITY))]
