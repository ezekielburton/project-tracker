# Cost-ledger brain for Digital Innovation: the rules for what a cost entry may
# look like and how summary numbers are computed. routes/costs.py is the HTTP
# layer on top, mirroring step_engine.py's split.
#
# dev_time amount is computed from DiSetting.dev_hourly_rate at save time —
# there's no historical rate table, so an entry is always priced at the current
# rate, and a later rate change never rewrites past entries.
#
# Entries are deletable but never editable: fix a wrong line by deleting and
# re-adding, so the ledger never silently rewrites itself. There is no
# update_cost_entry().

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiCostEntry, DiSetting, DI_COST_TYPES


DI_COST_TYPE_LABELS = {
    'dev_time': 'Dev Time',
    'claude': 'Claude',
    'hardware': 'Hardware',
    'licensing': 'Licensing',
}


def get_settings():
    """Fetch-or-create the singleton DiSetting row, lazily — a database with no
    row yet gets one with column defaults (rate 0, currency AED)."""
    settings = DiSetting.query.first()
    if not settings:
        settings = DiSetting()
        db.session.add(settings)
        db.session.flush()
    return settings


def cost_summary(di_project):
    """Everything the Cost breakdown modal needs: the ledger (newest first),
    per-type totals (amount/count/hours), the grand total, and projected profit
    when client_charge is set (None otherwise, so the template shows a dash)."""
    entries = (
        DiCostEntry.query
        .filter_by(di_project_id=di_project.id)
        .order_by(DiCostEntry.date.desc(), DiCostEntry.id.desc())
        .all()
    )

    by_type = {t: {'total': 0.0, 'count': 0, 'hours': 0.0} for t in DI_COST_TYPES}
    for entry in entries:
        row = by_type[entry.type]
        row['total'] += entry.amount
        row['count'] += 1
        if entry.hours:
            row['hours'] += entry.hours

    total_cost = sum(row['total'] for row in by_type.values())
    client_charge = di_project.client_charge
    projected_profit = (client_charge - total_cost) if client_charge is not None else None

    return {
        'entries': entries,
        'by_type': by_type,
        'total_cost': total_cost,
        'client_charge': client_charge,
        'projected_profit': projected_profit,
    }


def add_cost_entry(di_project, entry_date, cost_type, description=None, amount=None, hours=None, feature=None):
    """Validate and stage a new ledger line (the route commits). Raises
    ValueError on invalid input. dev_time entries are priced from the department
    hourly rate: hours (>0) and feature are required, amount is computed here.
    The other types are the reverse: amount (>0) is required, hours/feature
    forced to None."""
    if cost_type not in DI_COST_TYPES:
        raise ValueError(f"Unknown cost type '{cost_type}'.")
    if entry_date is None:
        raise ValueError("A date is required.")

    if cost_type == 'dev_time':
        if not hours or hours <= 0:
            raise ValueError("Hours must be greater than zero for Dev Time entries.")
        if feature is None:
            raise ValueError("A feature is required for Dev Time entries.")
        rate = get_settings().dev_hourly_rate or 0
        amount = round(hours * rate, 2)
    else:
        if not amount or amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        hours = None
        feature = None

    entry = DiCostEntry(
        di_project_id=di_project.id,
        date=entry_date,
        type=cost_type,
        di_feature_id=feature.id if feature else None,
        description=(description or '').strip() or None,
        amount=amount,
        hours=hours,
    )
    db.session.add(entry)
    return entry


def delete_cost_entry(entry):
    """Delete a ledger line (the route commits). No update_cost_entry — see
    module note."""
    db.session.delete(entry)
