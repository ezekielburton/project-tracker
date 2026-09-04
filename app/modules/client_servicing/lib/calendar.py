"""
Installation Calendar — risk derivation and the calendar data service.

The calendar is install-date driven: a project appears on its
Project.installation_date. Each install carries an effective risk — the
manual ClientServicing.risk when set (sticky), else derived from the
effective CS status vs. how close the install date is. Nothing here writes,
and nothing touches Project.project_status.
"""
from calendar import Calendar
from datetime import date, timedelta

from app.modules.client_servicing.lib.status import effective_cs_status


# Manual risk options (the dropdown), in severity order. Clearing reverts
# to the derived risk.
RISK_OPTIONS = ['On Track', 'Attention', 'At Risk', 'Done']

_RISK_MODIFIER = {
    'On Track': 'ontrack',
    'Attention': 'attention',
    'At Risk': 'atrisk',
    'Done': 'done',
}

# Effective-status labels that mean the install is finished (or past it) —
# risk reads Done regardless of the date.
_DONE_STATUSES = {
    'Installed', 'Prize Distribution', 'ED Closure',
    'Pending Invoice', 'Partial Invoicing', 'Invoiced',
}
# Production-ready — on track whatever the date, and what the "Ready" KPI
# counts.
_READY_STATUSES = {'In Production', 'Installed'}

# Auto-risk day thresholds (days until install, for a not-yet-ready job).
_ATRISK_DAYS = 2
_ATTENTION_DAYS = 7


def risk_modifier(label):
    return _RISK_MODIFIER.get(label, 'ontrack')


def _auto_risk(project, status_label, today):
    """Derived risk from effective status vs. install date."""
    if project.cancelled_at is not None:
        return 'Done'
    if status_label in _DONE_STATUSES:
        return 'Done'
    if status_label in _READY_STATUSES:
        return 'On Track'
    install = project.installation_date
    if install is None:
        return 'On Track'
    days = (install - today).days
    if days <= _ATRISK_DAYS:
        return 'At Risk'
    if days <= _ATTENTION_DAYS:
        return 'Attention'
    return 'On Track'


def effective_risk(project, status_label=None, today=None):
    """(label, css_modifier, is_auto). Manual ClientServicing.risk wins and
    is sticky; otherwise the derived risk. status_label may be passed in to
    avoid recomputing effective_cs_status per call."""
    if today is None:
        today = date.today()
    if status_label is None:
        status_label = effective_cs_status(project)[0]
    cs = project.client_servicing
    if cs and cs.risk:
        return (cs.risk, risk_modifier(cs.risk), False)
    label = _auto_risk(project, status_label, today)
    return (label, risk_modifier(label), True)


def build_install(project, today):
    """The per-install view model shared by the month drawer and the agenda
    row. Reads only relationships _base_projects already eager-loads, so it
    stays N+1-free across a list of projects."""
    cs = project.client_servicing
    status_label, status_class, status_is_auto = effective_cs_status(project)
    risk_label, risk_class, risk_is_auto = effective_risk(project, status_label, today)
    return {
        'id': project.id,
        'client': project.client_brand.name if project.client_brand else project.name,
        'name': project.name,
        'scope': cs.scope.name if (cs and cs.scope) else None,
        'qty': cs.install_qty if cs else None,
        'partial': status_label == 'Partial Invoicing',
        'install_date': project.installation_date,
        'status_label': status_label,
        'status_class': status_class,
        'status_is_auto': status_is_auto,
        'cs_status': cs.cs_status if cs else None,
        'risk_label': risk_label,
        'risk_class': risk_class,
        'risk_is_auto': risk_is_auto,
        'risk': cs.risk if cs else None,
        'cs_lead': project.cs_lead.name if project.cs_lead else None,
        'action_owner': cs.action_owner if cs else None,
        'next_action': cs.next_action if cs else None,
    }


def _kpis(installs, today):
    """Header counts. total/ready/attention/at-risk are over the passed
    installs (a month); next-7-days is relative to today across the same
    set."""
    horizon = today + timedelta(days=7)
    ready = attention = atrisk = next7 = 0
    for it in installs:
        if it['status_label'] in _READY_STATUSES:
            ready += 1
        if it['risk_label'] == 'Attention':
            attention += 1
        elif it['risk_label'] == 'At Risk':
            atrisk += 1
        if it['install_date'] and today <= it['install_date'] < horizon:
            next7 += 1
    return {
        'total': len(installs),
        'next7': next7,
        'ready': ready,
        'attention': attention,
        'atrisk': atrisk,
    }


# Risk order used to colour a day cell by its worst install.
_RISK_RANK = {'At Risk': 3, 'Attention': 2, 'On Track': 1, 'Done': 0}


def month_grid(projects, year, month, today):
    """Weeks of days (Mon-Sun) for the month, each day carrying its installs
    and worst-risk class, plus the month KPIs. `projects` is the eager-loaded
    base set; only those with an installation_date in the grid appear."""
    installs_by_day = {}
    month_installs = []
    for p in projects:
        d = p.installation_date
        if d is None:
            continue
        it = build_install(p, today)
        installs_by_day.setdefault(d, []).append(it)
        if d.year == year and d.month == month:
            month_installs.append(it)

    weeks = []
    for week in Calendar(firstweekday=0).monthdatescalendar(year, month):
        days = []
        for d in week:
            items = sorted(installs_by_day.get(d, []),
                           key=lambda i: -_RISK_RANK.get(i['risk_label'], 1))
            worst = items[0]['risk_class'] if items else None
            days.append({
                'date': d,
                'in_month': d.month == month,
                'is_today': d == today,
                'installs': items,
                'count': len(items),
                'worst': worst,
            })
        weeks.append(days)
    return weeks, _kpis(month_installs, today)


def agenda_groups(projects, today, days_ahead=30):
    """Upcoming installs from today, grouped by day (Today / Tomorrow /
    dated), plus the same KPIs computed over the current month."""
    horizon = today + timedelta(days=days_ahead)
    groups_map = {}
    month_installs = []
    for p in projects:
        d = p.installation_date
        if d is None:
            continue
        it = build_install(p, today)
        if d.year == today.year and d.month == today.month:
            month_installs.append(it)
        if today <= d <= horizon:
            groups_map.setdefault(d, []).append(it)

    groups = []
    for d in sorted(groups_map):
        items = sorted(groups_map[d], key=lambda i: -_RISK_RANK.get(i['risk_label'], 1))
        atrisk = sum(1 for i in items if i['risk_label'] == 'At Risk')
        groups.append({'date': d, 'installs': items, 'count': len(items), 'atrisk': atrisk})
    return groups, _kpis(month_installs, today)
