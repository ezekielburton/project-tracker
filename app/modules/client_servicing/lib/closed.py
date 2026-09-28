"""
Data for the Closed page, computed live from ClientServicing.closed_at.

Builds on _base_projects(), which keeps closed projects; _open_projects()
drops them.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import extract
from sqlalchemy.orm import joinedload

from app.modules.core.shared.models import Project

from app.modules.client_servicing.lib.money import money
from app.modules.client_servicing.models import ClientServicing
from app.modules.client_servicing.routes.table import _base_projects


_QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}


def _closed_query():
    """Every closed project, newest close first. _base_projects() excludes
    drafts and eager-loads the rows; closed_by is loaded here as only this page shows it."""
    return (
        _base_projects()
        .join(ClientServicing, ClientServicing.project_id == Project.id)
        .options(joinedload(Project.client_servicing).joinedload(ClientServicing.closed_by))
        .filter(ClientServicing.closed_at.isnot(None))
        .order_by(ClientServicing.closed_at.desc())
    )


def closed_projects(year=None, quarter=None, month=None):
    """Closed projects filtered by closing year, quarter and/or month (filters combine)."""
    query = _closed_query()
    if year:
        query = query.filter(extract('year', ClientServicing.closed_at) == year)
    if quarter in _QUARTER_MONTHS:
        query = query.filter(
            extract('month', ClientServicing.closed_at).in_(_QUARTER_MONTHS[quarter])
        )
    if month:
        query = query.filter(extract('month', ClientServicing.closed_at) == month)
    return query.all()


def closed_row(project):
    """One row on the Closed page. state comes from the model's
    close_invoice_state so the pill and the tests share one source."""
    cs = project.client_servicing
    return {
        'id': project.id,
        'client': project.client_brand.name if project.client_brand else None,
        'name': project.name,
        'cs': project.cs_lead.name if project.cs_lead else None,
        # None when unset so the table shows a dash; totals treat it as zero.
        'value': money(project.value) if project.value is not None else None,
        'closed_at': cs.closed_at,
        'closed_by': cs.closed_by.name if cs.closed_by else None,
        'state': cs.close_invoice_state,
        'invoice_date': cs.invoice_date,
    }


def month_groups(projects):
    """Rows grouped by closing month, each with a count and value total.
    Expects `projects` already sorted newest close first; it does not re-sort."""
    groups = []
    for project in projects:
        row = closed_row(project)
        closed_at = row['closed_at']
        key = (closed_at.year, closed_at.month)
        if not groups or groups[-1]['key'] != key:
            groups.append({
                'key': key,
                'label': date(key[0], key[1], 1).strftime('%B %Y'),
                'rows': [],
                'count': 0,
                'total': Decimal('0'),
            })
        group = groups[-1]
        group['rows'].append(row)
        group['count'] += 1
        group['total'] += row['value'] or Decimal('0')
    return groups


def kpis(today=None):
    """Count and value closed this week / month / quarter / year, as of
    today. Ignores the page's filters."""
    today = today or date.today()
    cards = [
        {'key': 'week', 'label': 'Closed · This Week',
         'start': today - timedelta(days=today.weekday())},
        {'key': 'month', 'label': 'Closed · This Month',
         'start': today.replace(day=1)},
        {'key': 'quarter', 'label': 'Closed · This Quarter',
         'start': date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)},
        {'key': 'year', 'label': 'Closed · This Year',
         'start': date(today.year, 1, 1)},
    ]
    for card in cards:
        card['count'] = 0
        card['value'] = Decimal('0')

    # A week can start in the previous year, so query from the earliest boundary.
    since = datetime.combine(min(card['start'] for card in cards), time.min)
    for project in _closed_query().filter(ClientServicing.closed_at >= since).all():
        cs = project.client_servicing
        closed_on = cs.closed_at.date()
        value = money(project.value)
        for card in cards:
            if closed_on >= card['start']:
                card['count'] += 1
                card['value'] += value
    return cards
