"""
Accounts: every job grouped by client or by CS lead, invoiced history
included, plus each lead's load for a billing month. Read-only.

Loads through base_projects() and buckets months with summary.billing_month,
so its figures match the Monthly Summary. Invoicing figures are left out for
anyone without can_view_finance.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import selectinload

from app.modules.core.shared.models import Project, ProjectSecondaryCS
from app.modules.client_servicing.lib.access import can_view_finance
from app.modules.client_servicing.lib.money import money
from app.modules.client_servicing.lib.project_sets import base_projects
from app.modules.client_servicing.lib.status import effective_cs_status
from app.modules.client_servicing.lib.summary import billing_month, has_lpo, is_invoiced


GROUPS = ('client', 'lead')
NO_CLIENT = 'No client'
NO_LEAD = 'No CS lead'


def parse_month(raw):
    """'YYYY-MM' as (year, month); anything else is None (All time)."""
    try:
        year, month = (int(part) for part in (raw or '').split('-'))
        date(year, month, 1)
    except ValueError:
        return None
    return (year, month)


def month_value(month):
    return f'{month[0]:04d}-{month[1]:02d}'


def month_label(month):
    return date(month[0], month[1], 1).strftime('%b %Y')


def _load_projects():
    """Every non-draft job with its secondary CS, in a fixed number of queries."""
    return (base_projects()
            .options(selectinload(Project.secondary_cs_assignments)
                     .joinedload(ProjectSecondaryCS.user))
            .all())


def _row(project, finance):
    cs = project.client_servicing
    label, css, _auto = effective_cs_status(project)
    row = {
        'id': project.id,
        'project': project.name,
        'job_number': project.job_number,
        'scope': cs.scope.name if (cs and cs.scope) else None,
        'client_id': project.client_id,
        'client': project.client_brand.name if project.client_brand else NO_CLIENT,
        'lead_id': project.cs_lead_id,
        'lead': project.cs_lead.name if project.cs_lead else NO_LEAD,
        # Shown as a tag; the job still counts once, under its lead.
        'secondary': sorted((a.user.name for a in project.secondary_cs_assignments
                             if a.user and a.user_id != project.cs_lead_id), key=str.casefold),
        'status_label': label,
        'status_class': css,
        'install': project.installation_date,
        'value': money(project.value),
        'cancelled': project.cancelled_at is not None,
    }
    if finance:
        row['invoiced'] = money(cs.invoice_amount) if is_invoiced(cs) else None
    return row


def _groups(rows, group, finance):
    """Rows bucketed by client or lead; groups and their rows largest value first."""
    key, name, other = (('client_id', 'client', 'lead') if group == 'client'
                        else ('lead_id', 'lead', 'client'))
    buckets = {}
    for row in rows:
        buckets.setdefault((row[key], row[name]), []).append(row)
    out = []
    for (group_id, group_name), members in buckets.items():
        members.sort(key=lambda r: (-r['value'], r['project'].casefold()))
        entry = {
            'id': group_id,
            'name': group_name,
            'key': 'none' if group_id is None else str(group_id),
            'count': len(members),
            'others': sorted({r[other] for r in members}, key=str.casefold),
            'value': sum((r['value'] for r in members), Decimal('0')),
            'rows': members,
        }
        if finance:
            entry['invoiced'] = sum((r['invoiced'] or Decimal('0') for r in members), Decimal('0'))
        out.append(entry)
    out.sort(key=lambda g: (-g['value'], g['name'].casefold()))
    return out


def _load(projects, finance):
    """(rows, total): one row per CS lead, largest value first. Active = not
    invoiced and not cancelled; No LPO skips cancelled jobs."""
    leads = {}
    for p in projects:
        cs = p.client_servicing
        row = leads.get(p.cs_lead_id)
        if row is None:
            row = {'lead_id': p.cs_lead_id, 'lead': p.cs_lead.name if p.cs_lead else NO_LEAD,
                   'jobs': 0, 'active': 0, 'no_lpo': 0, 'value': Decimal('0')}
            if finance:
                row.update(invoiced=0, invoiced_amount=Decimal('0'))
            leads[p.cs_lead_id] = row
        cancelled = p.cancelled_at is not None
        invoiced = is_invoiced(cs)
        row['jobs'] += 1
        row['value'] += money(p.value)
        if not invoiced and not cancelled:
            row['active'] += 1
        if not cancelled and not has_lpo(cs):
            row['no_lpo'] += 1
        if finance and invoiced:
            row['invoiced'] += 1
            row['invoiced_amount'] += money(cs.invoice_amount)
    rows = sorted(leads.values(), key=lambda r: (-r['value'], r['lead'].casefold()))
    keys = ['jobs', 'active', 'no_lpo', 'value'] + (['invoiced', 'invoiced_amount'] if finance else [])
    total = {k: sum((r[k] for r in rows), Decimal('0') if k in ('value', 'invoiced_amount') else 0)
             for k in keys}
    return rows, total


def _options(projects):
    """Client, lead and billing-month choices from every job, whatever the filters."""
    clients = {(p.client_id, p.client_brand.name) for p in projects if p.client_brand}
    leads = {(p.cs_lead_id, p.cs_lead.name) for p in projects if p.cs_lead}
    months = sorted({m for m in (billing_month(p) for p in projects) if m}, reverse=True)
    return {
        'clients': [{'id': i, 'name': n} for i, n in sorted(clients, key=lambda c: c[1].casefold())],
        'leads': [{'id': i, 'name': n} for i, n in sorted(leads, key=lambda c: c[1].casefold())],
        'months': [{'value': month_value(m), 'label': month_label(m)} for m in months],
    }


def accounts_view(user, group='client', client_id=None, lead_id=None, month=None):
    """The Accounts page. `month` is (year, month) or None for All time; the
    client and lead filters narrow the list and tiles, the load panel follows
    the month only. Invoicing figures are absent unless can_view_finance(user)."""
    group = group if group in GROUPS else 'client'
    finance = can_view_finance(user)
    projects = _load_projects()
    in_month = [p for p in projects if month is None or billing_month(p) == month]
    listed = [p for p in in_month
              if (client_id is None or p.client_id == client_id)
              and (lead_id is None or p.cs_lead_id == lead_id)]
    rows = [_row(p, finance) for p in listed]
    groups = _groups(rows, group, finance)

    kpis = {'jobs': len(rows), 'value': sum((g['value'] for g in groups), Decimal('0'))}
    if finance:
        kpis['invoiced'] = sum((g['invoiced'] for g in groups), Decimal('0'))
        kpis['not_invoiced'] = sum((r['value'] for r in rows
                                    if r['invoiced'] is None and not r['cancelled']), Decimal('0'))
    load_rows, load_total = _load(in_month, finance)
    return {
        'group': group,
        'finance': finance,
        'groups': groups,
        'kpis': kpis,
        'load': load_rows,
        'load_total': load_total,
        'month': month_value(month) if month else '',
        'month_label': month_label(month) if month else 'All time',
        'client_id': client_id,
        'lead_id': lead_id,
        'options': _options(projects),
    }
