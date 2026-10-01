"""
Rollups for Invoicing > Monthly Summary, computed live from the finance fields.
Builds on base_projects() (drafts excluded, closed kept). Money is returned
as Decimal; the template formats it.

A project's value is Project.value, the same figure the Table, Invoicing and
Closed pages use.
"""
from datetime import date
from decimal import Decimal

from app.modules.client_servicing.lib.money import money
from app.modules.client_servicing.lib.project_sets import base_projects


# Validation states that count a project as "stuck" even when it has an LPO.
_STUCK_VALIDATION = {'no_lpo', 'overdue'}


def _billing_month(project):
    """(year, month) a project counts in: invoice_date, else invoice_month_date,
    else removal_date. None (in no month) if all are unset.
    Do not add Project.first_output_deadline: it is a design deadline, not billing."""
    cs = project.client_servicing
    if cs is None:
        return None
    d = cs.invoice_date or cs.invoice_month_date or cs.removal_date
    return (d.year, d.month) if d else None


def _has_lpo(cs):
    return bool(cs and cs.lpo)


def _is_invoiced(cs):
    return bool(cs and cs.invoice_date)


def _is_stuck(cs):
    """No LPO at all, or an LPO whose validation is flagged No LPO / Overdue."""
    if not _has_lpo(cs):
        return True
    return cs.validation_status in _STUCK_VALIDATION





def year_summary(year):
    """(rows, total) for a calendar year: one row per month plus the year total.
    Row keys: month, label, pipeline, confirmed, invoiced, progress
    (invoiced/confirmed %), stuck, stuck_amount."""
    buckets = {m: {'pipeline': Decimal('0'), 'confirmed': Decimal('0'),
                   'invoiced': Decimal('0'), 'stuck': 0,
                   'stuck_amount': Decimal('0')} for m in range(1, 13)}

    for p in base_projects().all():
        bm = _billing_month(p)
        if not bm or bm[0] != year:
            continue
        cs = p.client_servicing
        b = buckets[bm[1]]
        b['pipeline'] += money(p.value)
        if _has_lpo(cs):
            b['confirmed'] += money(p.value)
        if _is_invoiced(cs):
            b['invoiced'] += money(cs.invoice_amount if cs else None)
        if _is_stuck(cs):
            b['stuck'] += 1
            b['stuck_amount'] += money(p.value)

    rows = []
    for m in range(1, 13):
        b = buckets[m]
        progress = round(float(b['invoiced'] / b['confirmed'] * 100)) if b['confirmed'] else 0
        rows.append({
            'month': m,
            'label': date(year, m, 1).strftime('%b'),
            'pipeline': b['pipeline'],
            'confirmed': b['confirmed'],
            'invoiced': b['invoiced'],
            'progress': progress,
            'stuck': b['stuck'],
            'stuck_amount': b['stuck_amount'],
        })

    total = {
        'pipeline': sum((r['pipeline'] for r in rows), Decimal('0')),
        'confirmed': sum((r['confirmed'] for r in rows), Decimal('0')),
        'invoiced': sum((r['invoiced'] for r in rows), Decimal('0')),
        'stuck': sum(r['stuck'] for r in rows),
        'stuck_amount': sum((r['stuck_amount'] for r in rows), Decimal('0')),
    }
    return rows, total


def stuck_this_month(year, month):
    """The month's stuck projects, largest value first. Same set the rollup
    counts (closed included), so the panel's count and list agree. `closed`
    tells the Dashboard to link to the Closed page, as closed projects are
    not on the Invoicing table."""
    out = []
    for p in base_projects().all():
        if _billing_month(p) != (year, month):
            continue
        cs = p.client_servicing
        if not _is_stuck(cs):
            continue
        out.append({
            'id': p.id,
            'client': p.client_brand.name if p.client_brand else None,
            'project': p.name,
            'value': money(p.value),
            'reason': 'Overdue' if (cs and cs.validation_status == 'overdue') else 'No LPO',
            'closed': cs is not None and cs.closed_at is not None,
            'closed_at': cs.closed_at if cs is not None else None,
        })
    out.sort(key=lambda row: -row['value'])
    return out


def due_this_month(year, month):
    """The month's projects not yet invoiced. validation is returned raw;
    the route maps it to a pill."""
    out = []
    for p in base_projects().all():
        if _billing_month(p) != (year, month):
            continue
        cs = p.client_servicing
        if _is_invoiced(cs):
            continue
        out.append({
            'client': p.client_brand.name if p.client_brand else None,
            'project': p.name,
            'cs': p.cs_lead.name if p.cs_lead else None,
            'value': p.value,
            'validation': cs.validation_status if cs else None,
        })
    return out
