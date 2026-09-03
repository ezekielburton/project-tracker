# Digital Innovation — "brain" for the cost ledger (Phase 3). Every rule
# about what a cost entry is allowed to look like and how the summary
# numbers are computed lives here, in one place — routes/costs.py is just
# the HTTP layer on top of it, mirroring step_engine.py's split (brain A)
# for this brain.
#
# DiCostEntry.amount for type='dev_time' is computed here from
# DiSetting.dev_hourly_rate at the moment the entry is SAVED — there's no
# historical rate table, so a backdated `date` does NOT retroactively look
# up what the rate was on that day; it's always priced at today's rate.
# A later rate change never rewrites a past entry's amount (per the
# model's own docstring), but an entry logged today for hours worked last
# month is still priced at today's rate, not last month's.
#
# Entries are deletable but never editable once saved (Ezekiel, 1 Sep
# 2026) — if a line is wrong, delete it and add a corrected one, so the
# ledger never silently rewrites history. There is deliberately no
# update_cost_entry() here.

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiCostEntry, DiSetting, DI_COST_TYPES


DI_COST_TYPE_LABELS = {
    'dev_time': 'Dev Time',
    'claude': 'Claude',
    'hardware': 'Hardware',
    'licensing': 'Licensing',
}


def get_settings():
    """Fetch-or-create the singleton DiSetting row. Created lazily rather
    than seeded by a migration, so a fresh/older database with no row yet
    just gets one with the column defaults (rate 0, currency AED) instead
    of erroring."""
    settings = DiSetting.query.first()
    if not settings:
        settings = DiSetting()
        db.session.add(settings)
        db.session.flush()
    return settings


def cost_summary(di_project):
    """Everything the Cost breakdown modal needs: the ledger itself
    (newest first), per-type totals (amount/count/hours), the grand
    total, and — when the project has a client_charge set — the
    projected profit. projected_profit is None (not 0) when
    client_charge is unset, so the template can show a dash instead of a
    misleading number."""
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
    """Validates and stages a new ledger line (route commits, same
    convention as step_engine.py). Raises ValueError on any invalid
    input.

    type='dev_time' entries are priced from the department's hourly rate
    rather than a typed-in amount: hours is required (>0) and feature is
    required (dev hours are tracked per-feature — see DiCostEntry's
    docstring), and amount is computed here, not accepted from the
    caller. The other three types are the reverse: amount is required
    (>0), and hours/feature are forced to None since they're project-
    level costs with no per-hour or per-feature meaning."""
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
    """Deletes a ledger line (route commits). No update_cost_entry — see
    module docstring."""
    db.session.delete(entry)
