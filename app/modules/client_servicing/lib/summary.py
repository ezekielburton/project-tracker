"""
Monthly Summary rollup for the Invoicing tab. Everything here is computed
live from the finance fields — nothing stored. Drafts are excluded via the
shared _base_projects(). Money values are Decimals; the template formats them.
"""
from datetime import date
from decimal import Decimal

from app.modules.client_servicing.routes.table import _base_projects


# Validation states that count a project as "stuck" even when it has an LPO.
_STUCK_VALIDATION = {'no_lpo', 'overdue'}


def _billing_month(project):
    """(year, month) a project is counted in: its invoice month if invoiced,
    else its removal month, else its due-date month. None if it has none of
    those dates (then it isn't in any month's rollup)."""
    cs = project.client_servicing
    d = (cs.invoice_date if cs else None) or (cs.removal_date if cs else None) or project.first_output_deadline
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


def _dec(v):
    return v if v is not None else Decimal('0')


def year_summary(year):
    """(rows, total) for one calendar year — one row per month plus a
    full-year total. Each row: month, label, pipeline, confirmed, invoiced,
    progress (invoiced/confirmed %), stuck count."""
    buckets = {m: {'pipeline': Decimal('0'), 'confirmed': Decimal('0'),
                   'invoiced': Decimal('0'), 'stuck': 0} for m in range(1, 13)}

    for p in _base_projects().all():
        bm = _billing_month(p)
        if not bm or bm[0] != year:
            continue
        cs = p.client_servicing
        b = buckets[bm[1]]
        b['pipeline'] += _dec(cs.project_value if cs else None)
        if _has_lpo(cs):
            b['confirmed'] += _dec(cs.project_value if cs else None)
        if _is_invoiced(cs):
            b['invoiced'] += _dec(cs.invoice_amount if cs else None)
        if _is_stuck(cs):
            b['stuck'] += 1

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
        })

    total = {
        'pipeline': sum((r['pipeline'] for r in rows), Decimal('0')),
        'confirmed': sum((r['confirmed'] for r in rows), Decimal('0')),
        'invoiced': sum((r['invoiced'] for r in rows), Decimal('0')),
        'stuck': sum(r['stuck'] for r in rows),
    }
    return rows, total


def due_this_month(year, month):
    """The selected month's projects that aren't invoiced yet — the ones
    still needing action. validation_status is returned raw; the route maps
    it to a pill."""
    out = []
    for p in _base_projects().all():
        if _billing_month(p) != (year, month):
            continue
        cs = p.client_servicing
        if _is_invoiced(cs):
            continue
        out.append({
            'client': p.client_brand.name if p.client_brand else None,
            'project': p.name,
            'cs': p.cs_lead.name if p.cs_lead else None,
            'value': cs.project_value if cs else None,
            'validation': cs.validation_status if cs else None,
        })
    return out
