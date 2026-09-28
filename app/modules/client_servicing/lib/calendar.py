"""
Installation Calendar data: risk derivation and the month/agenda view models.

A project appears on its Project.installation_date. Its risk is the manual
ClientServicing.risk when set, else derived from CS status vs. days to install.
Read-only; never touches Project.project_status.
"""
from calendar import Calendar
from datetime import date, timedelta

from app.modules.client_servicing.lib.status import effective_cs_status


# Manual risk dropdown options. Clearing the field reverts to the derived risk.
RISK_OPTIONS = ['On Track', 'Attention', 'At Risk', 'Done']

_RISK_MODIFIER = {
    'On Track': 'ontrack',
    'Attention': 'attention',
    'At Risk': 'atrisk',
    'Done': 'done',
}

# Statuses at or past install: risk reads Done whatever the date.
_DONE_STATUSES = {
    'Installed', 'Prize Distribution', 'ED Closure',
    'Pending Invoice', 'Partial Invoicing', 'Invoiced',
}
# Production-ready: On Track whatever the date. The "Ready" KPI counts these.
_READY_STATUSES = {'In Production', 'Installed'}

# Auto-risk thresholds in days until install, for jobs not yet ready.
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
    """(label, css_modifier, is_auto). Manual ClientServicing.risk wins, else
    the derived risk. Pass status_label to skip recomputing the CS status."""
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
    """Per-install view model for the month drawer and the agenda row. Reads
    only relationships _base_projects eager-loads, so no N+1 queries."""
    cs = project.client_servicing
    status_label, status_class, status_is_auto = effective_cs_status(project)
    risk_label, risk_class, risk_is_auto = effective_risk(project, status_label, today)
    return {
        'id': project.id,
        # Closed jobs stay on the calendar, faded and with no editable cells.
        'closed': cs is not None and cs.closed_at is not None,
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
    """Header counts over the passed installs (a month). next7 counts those
    installing in the 7 days from today."""
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
    """(weeks, kpis) for the month. Weeks run Mon-Sun; each day carries its
    installs and worst-risk class. `projects` must be the eager-loaded base set."""
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
    """(groups, kpis): installs from today to `days_ahead`, grouped by day,
    plus the KPIs for the current month."""
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
