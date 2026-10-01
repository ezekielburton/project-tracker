"""
Client Servicing dashboard: the module's landing panels and its feed for the
global Dashboard. Read-only.

Loads the active set through active_projects(), the loader Invoicing By Project
shares, and reuses the Calendar and Invoicing helpers so numbers match those pages.
Finance figures need can_view_finance; page access alone is not enough.
"""
from datetime import date, timedelta

from flask import url_for

from app.modules.client_servicing.lib.access import (
    can_access_client_servicing, can_view_finance,
)
from app.modules.client_servicing.lib.status import effective_cs_status
from app.modules.client_servicing.lib.calendar import effective_risk, build_install
from app.modules.client_servicing.lib.summary import year_summary, due_this_month, stuck_this_month
from app.modules.client_servicing.lib.data_gaps import MISSING_DATA_CHIP, missing_fields
from app.modules.client_servicing.lib.project_sets import active_projects


# Days ahead the feed looks for installs; rows shown in Upcoming Installs.
_FEED_INSTALL_DAYS = 7
_UPCOMING_LIMIT = 8

# Status label (derived or manual) -> family for the Status Spread panel.
_STATUS_FAMILY = {
    'Briefing': 'In Design', 'Survey': 'In Design', 'In Design': 'In Design',
    'KV in Progress': 'In Design', 'AW in Progress': 'In Design',
    '3D in Progress': 'In Design', 'TD in Progress': 'In Design',
    'Submitted to Client': 'Pending Approval', 'Pending Approval': 'Pending Approval',
    'Pre-Production': 'Pre-Production', 'Pending Quotation': 'Pre-Production',
    'Pending LPO': 'Pre-Production', 'Pending Production': 'Pre-Production',
    'In Production': 'In Production',
    'Installed': 'Post-Install', 'Prize Distribution': 'Post-Install',
    'ED Closure': 'Post-Install',
    'Pending Invoice': 'Invoicing', 'Partial Invoicing': 'Invoicing',
    'Invoiced': 'Invoicing',
    'On Hold': 'On Hold',
}
_FAMILY_ORDER = [
    'In Design', 'Pending Approval', 'Pre-Production', 'In Production',
    'Post-Install', 'Invoicing', 'On Hold',
]

_URGENCY_RANK = {'urgent': 0, 'warning': 1, 'info': 2}


def _signal_sort(item):
    return (_URGENCY_RANK.get(item['urgency'], 3), item['date'] or date.max)


def _snapshot(active, today):
    """Status and risk resolved once per project, for every panel to share."""
    snap = []
    for p in active:
        status = effective_cs_status(p)[0]
        risk = effective_risk(p, status, today)[0]
        snap.append({'p': p, 'status': status, 'risk': risk})
    return snap


# --- links -----------------------------------------------------------------

def _missing_data_link():
    """The Table with its Missing-data chip on."""
    return url_for('client_servicing.table', chip=MISSING_DATA_CHIP)


def _invoicing_project_link(project_id):
    """Invoicing > By Project, focused on one project."""
    return url_for('client_servicing.invoicing', project=project_id)


def _closed_project_link(project_id, closed_at):
    """The Closed page filtered to the project's closing month (so the row is
    on screen) and focused on it."""
    params = {'project': project_id}
    if closed_at is not None:
        params['year'] = closed_at.year
        params['month'] = closed_at.month
    return url_for('client_servicing.closed', **params)


def _stuck_link(row):
    """Link to the page that shows the row: Closed if closed, else Invoicing."""
    if row['closed']:
        return _closed_project_link(row['id'], row['closed_at'])
    return _invoicing_project_link(row['id'])


def _calendar_link(d):
    return url_for('client_servicing.calendar', month='%04d-%02d' % (d.year, d.month))


def _invoicing_link(today):
    return url_for('client_servicing.invoicing_summary', year=today.year, month=today.month)


# --- panels ----------------------------------------------------------------

def _kpi_band(snap, today, show_finance, month_row):
    horizon = today + timedelta(days=7)
    installs_month = next7 = at_risk = 0
    for r in snap:
        d = r['p'].installation_date
        if d and d.year == today.year and d.month == today.month:
            installs_month += 1
        if d and today <= d < horizon:
            next7 += 1
        if r['risk'] == 'At Risk':
            at_risk += 1
    band = {
        'active': len(snap), 'installs_month': installs_month,
        'next7': next7, 'at_risk': at_risk,
    }
    if show_finance and month_row is not None:
        band['pipeline'] = month_row['pipeline']
        band['stuck'] = month_row['stuck']
    return band


def _status_spread(snap):
    counts = {fam: 0 for fam in _FAMILY_ORDER}
    for r in snap:
        fam = _STATUS_FAMILY.get(r['status'])
        if fam:
            counts[fam] += 1
    return {
        'total': sum(counts.values()),
        'families': [{'name': fam, 'count': counts[fam]} for fam in _FAMILY_ORDER],
    }


def _workload(snap):
    by_lead = {}
    for r in snap:
        lead = r['p'].cs_lead
        if not lead:
            continue
        w = by_lead.setdefault(lead.id, {'name': lead.name, 'active': 0, 'at_risk': 0})
        w['active'] += 1
        if r['risk'] == 'At Risk':
            w['at_risk'] += 1
    return sorted(by_lead.values(), key=lambda w: (-w['active'], w['name']))


def _upcoming(snap, today):
    dated = [r for r in snap if r['p'].installation_date and r['p'].installation_date >= today]
    dated.sort(key=lambda r: r['p'].installation_date)
    return [build_install(r['p'], today) for r in dated[:_UPCOMING_LIMIT]]


def _data_gaps(snap):
    """Jobs missing an install date or value, counted once each. Shown as one
    strip so they can't bury the risk and money rows."""
    count = sum(1 for r in snap if missing_fields(r['p']))
    return {'count': count, 'link': _missing_data_link()}


def _finance_signals(due, today):
    """Urgent/feed rows from the month's uninvoiced projects (the same set
    Invoicing > Monthly Summary uses)."""
    link = _invoicing_link(today)
    items = []
    for d in due:
        validation = d.get('validation')
        if validation == 'overdue':
            kind, urgency, tag = 'invoice_overdue', 'urgent', 'Overdue'
        elif validation == 'no_lpo':
            kind, urgency, tag = 'lpo_outstanding', 'warning', 'No LPO'
        else:
            kind, urgency, tag = 'invoice_due', 'warning', 'Unbilled'
        items.append({
            'source': 'client_servicing', 'kind': kind, 'title': d['project'],
            'detail': '%s · %s' % (tag, d['client'] or '—'),
            'link': link, 'urgency': urgency, 'date': None,
        })
    return items


def _urgent_actions(snap, due, today, show_finance):
    """At-risk installs plus, for finance viewers, the month's money items.
    Missing data is counted separately by _data_gaps."""
    items = []
    for r in snap:
        p = r['p']
        if r['risk'] in ('At Risk', 'Attention') and p.installation_date:
            items.append({
                'source': 'client_servicing', 'kind': 'install_risk', 'title': p.name,
                'detail': '%s · installs %s' % (r['risk'], p.installation_date.strftime('%d %b')),
                'link': _calendar_link(p.installation_date),
                'urgency': 'urgent' if r['risk'] == 'At Risk' else 'warning',
                'date': p.installation_date,
            })
    if show_finance:
        items += _finance_signals(due, today)
    items.sort(key=_signal_sort)
    return items


def _feed_installs(snap, today):
    horizon = today + timedelta(days=_FEED_INSTALL_DAYS)
    items = []
    for r in snap:
        d = r['p'].installation_date
        if not d or not (today <= d <= horizon):
            continue
        urgency = {'At Risk': 'urgent', 'Attention': 'warning'}.get(r['risk'], 'info')
        items.append({
            'source': 'client_servicing', 'kind': 'install_upcoming', 'title': r['p'].name,
            'detail': 'Installs %s' % d.strftime('%d %b'), 'link': _calendar_link(d),
            'urgency': urgency, 'date': d,
        })
    return items


# --- public ----------------------------------------------------------------

def dashboard_context(user):
    """Context for the CS dashboard template. Finance panels are filled only
    for finance viewers."""
    today = date.today()
    show_finance = can_view_finance(user)
    snap = _snapshot(active_projects().all(), today)

    month_row = due = None
    stuck = []
    if show_finance:
        rows, _ = year_summary(today.year)
        month_row = rows[today.month - 1]
        due = due_this_month(today.year, today.month)
        # Same set the rollup counts, so the panel's count and names agree.
        stuck = [dict(row, link=_stuck_link(row)) for row in
                 stuck_this_month(today.year, today.month)]

    return {
        'show_finance': show_finance,
        'today': today,
        'kpis': _kpi_band(snap, today, show_finance, month_row),
        'status_spread': _status_spread(snap),
        'workload': _workload(snap),
        'upcoming': _upcoming(snap, today),
        'urgent_actions': _urgent_actions(snap, due or [], today, show_finance),
        'data_gaps': _data_gaps(snap),
        'invoicing_health': month_row,
        'stuck_projects': stuck,
    }


def feed_items(user):
    """Feed for the global Dashboard: upcoming installs plus, for finance
    viewers, the month's No LPO / unbilled / overdue items. Empty without CS access."""
    if not can_access_client_servicing(user):
        return []
    today = date.today()
    snap = _snapshot(active_projects().all(), today)
    items = _feed_installs(snap, today)
    if can_view_finance(user):
        items += _finance_signals(due_this_month(today.year, today.month), today)
    items.sort(key=_signal_sort)
    return items