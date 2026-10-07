"""
Client Servicing data for the Reports module: closes, invoices, installs and
missing data. Loads through the CS project sets so the numbers match the CS pages.
"""
from app.modules.core.shared.lib.timezone import to_dubai
from app.modules.core.shared.models import Project
from app.modules.client_servicing.lib.calendar import DONE_STATUSES
from app.modules.client_servicing.lib.data_gaps import missing_fields
from app.modules.client_servicing.lib.project_sets import active_projects, base_projects
from app.modules.client_servicing.lib.status import effective_cs_status
from app.modules.client_servicing.models import ClientServicing


def _people(project):
    """Who a CS job is credited to: its CS lead and its project owner."""
    return [uid for uid in (project.cs_lead_id, project.project_owner_id) if uid]


def _row(project, **extra):
    return {'project_id': project.id, 'name': project.name, 'people': _people(project), **extra}


def _with_cs():
    return base_projects().join(ClientServicing, ClientServicing.project_id == Project.id)


def closed_between(start_utc, end_utc):
    """Jobs closed in [start_utc, end_utc), naive UTC."""
    rows = _with_cs().filter(ClientServicing.closed_at >= start_utc,
                             ClientServicing.closed_at < end_utc)
    return [_row(p, closed_on=to_dubai(p.client_servicing.closed_at).date()) for p in rows]


def invoiced_between(start, end):
    """Jobs invoiced on dates start..end (inclusive), with the amount."""
    rows = _with_cs().filter(ClientServicing.invoice_date >= start,
                             ClientServicing.invoice_date <= end,
                             ClientServicing.invoice_needed.isnot(False))
    return [_row(p, amount=p.client_servicing.invoice_amount or 0) for p in rows]


def waiting_to_invoice(today):
    """Closed jobs still waiting for an invoice, longest wait first."""
    rows = _with_cs().filter(ClientServicing.closed_at.isnot(None),
                             ClientServicing.invoice_date.is_(None),
                             ClientServicing.invoice_needed.isnot(False))
    out = []
    for p in rows:
        closed_on = to_dubai(p.client_servicing.closed_at).date()
        out.append(_row(p, closed_on=closed_on, days=(today - closed_on).days))
    return sorted(out, key=lambda r: r['days'], reverse=True)


def installs_between(start, end):
    """Jobs whose install date falls in start..end, and whether each has
    reached Installed or later (or closed) by now."""
    rows = base_projects().filter(Project.installation_date >= start,
                                  Project.installation_date <= end,
                                  Project.cancelled_at.is_(None))
    out = []
    for p in rows:
        cs = p.client_servicing
        done = bool(cs and cs.closed_at) or effective_cs_status(p)[0] in DONE_STATUSES
        out.append(_row(p, install_on=p.installation_date, done=done))
    return out


def active_jobs():
    """Every active job and what it's missing (empty when complete)."""
    return [_row(p, missing=missing_fields(p)) for p in active_projects()]


def incomplete():
    """Active jobs missing data, with what each one is missing."""
    return [r for r in active_jobs() if r['missing']]
