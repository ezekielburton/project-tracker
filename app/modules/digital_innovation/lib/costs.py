# Cost-ledger rules: validating entries, computing summaries, and the Settings
# screen's rate/currency. routes/costs.py and routes/templates.py (Settings)
# are the HTTP layers.
#
# dev_time amounts are priced from DiSetting.dev_hourly_rate at save time, so a
# later rate change never rewrites past entries.
#
# Entries can be deleted but not edited; fix a wrong line by deleting and
# re-adding it.

import math

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiCostEntry, DiSetting, DI_COST_TYPES


DI_COST_TYPE_LABELS = {
    'dev_time': 'Dev Time',
    'claude': 'Claude',
    'hardware': 'Hardware',
    'licensing': 'Licensing',
}


def get_settings():
    """The single DiSetting row, created with defaults (rate 0, AED) if
    missing."""
    settings = DiSetting.query.first()
    if not settings:
        settings = DiSetting()
        db.session.add(settings)
        db.session.flush()
    return settings


def update_settings(raw_rate, raw_currency):
    """Validates Settings-screen input and, when it is good, stages it on the
    DiSetting row; the caller commits. Returns a dict of field name -> error
    message, empty on success. Nothing is changed when any field fails."""
    errors = {}

    rate = None
    # bool is an int subclass, so True would otherwise save as 1.
    if not isinstance(raw_rate, bool):
        try:
            rate = float(raw_rate)
        except (TypeError, ValueError):
            rate = None
    if rate is None or not math.isfinite(rate):
        errors['dev_hourly_rate'] = 'Dev hourly rate must be a number.'
    elif rate < 0:
        errors['dev_hourly_rate'] = 'Dev hourly rate cannot be negative.'

    currency = raw_currency.strip().upper() if isinstance(raw_currency, str) else ''
    if not currency:
        errors['currency'] = 'Currency is required.'
    elif len(currency) > 10:
        errors['currency'] = 'Currency must be 10 characters or fewer.'

    if errors:
        return errors

    settings = get_settings()
    # + 0.0 turns a rounded -0.0 into 0.0 so it never displays as "-0.00".
    settings.dev_hourly_rate = round(rate, 2) + 0.0
    settings.currency = currency
    return errors


def cost_summary(di_project):
    """Cost breakdown data: the ledger (newest first), per-type totals, the
    grand total, and projected profit (None when client_charge is unset)."""
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
    """Validates and stages a ledger line; the caller commits. Raises
    ValueError on bad input. dev_time needs hours and a feature and has its
    amount computed; other types need an amount and drop hours/feature."""
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
    """Deletes a ledger line; the caller commits."""
    db.session.delete(entry)
