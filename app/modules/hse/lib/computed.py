"""
Every derived value in the module, computed at read time. Derived values
are never written to the database.
"""

import re
from datetime import date, timedelta

from app.modules.hse.lib.schedule import add_months


# Days before expiry at which an item reads "Expiring soon".
EXPIRING_SOON_DAYS = 30

# Severity ranking, used for sorting and for the workbook's severity score.
SEVERITY_SCORE = {'Low': 1, 'Medium': 2, 'High': 3, 'Critical': 4}

# Days an entry of each severity may stay open before it is late.
SLA_DAYS = {'Critical': 4, 'High': 7, 'Medium': 15, 'Low': 30}


def _today(today=None):
    return today or date.today()


def days_open(entry, today=None):
    """Days open: to today while open, to closed_at once closed. None
    without an entry_date."""
    if entry.entry_date is None:
        return None
    end = entry.closed_at or _today(today)
    return (end - entry.entry_date).days


def days_to_expiry(entry, today=None):
    """Days until due_at — negative once it has passed. None when the
    entry has no due date."""
    if entry.due_at is None:
        return None
    return (entry.due_at - _today(today)).days


def expiry_status(entry, today=None):
    """Valid / Expiring soon / Expired, from due_at alone. The status for
    status_source='expiry' registers."""
    remaining = days_to_expiry(entry, today)
    if remaining is None:
        return None
    if remaining < 0:
        return 'Expired'
    if remaining <= EXPIRING_SOON_DAYS:
        return 'Expiring soon'
    return 'Valid'


def severity_score(entry):
    """The workbook's numeric severity. None for an unset severity."""
    return SEVERITY_SCORE.get(entry.severity)


def days_waiting(entry, today=None):
    """Days the entry has been parked with someone else, 0 when it is not."""
    if entry.waiting_since is None:
        return 0
    end = entry.closed_at or _today(today)
    return max(0, (end - entry.waiting_since).days)


def days_owned(entry, today=None):
    """Days open less days parked with someone else. Used by the
    performance page."""
    total = days_open(entry, today)
    if total is None:
        return None
    return max(0, total - days_waiting(entry, today))


def sla_days(entry):
    """The SLA for this entry's severity, or None when severity is unset."""
    return SLA_DAYS.get(entry.severity)


def closed_on_time(entry, today=None):
    """True when a closed entry met its SLA, measured on days_owned (time
    parked with someone else is excluded). None when open or no severity."""
    if entry.closed_at is None:
        return None
    allowed = sla_days(entry)
    if allowed is None:
        return None
    return days_owned(entry, today) <= allowed


def effective_status(entry, reg, today=None):
    """The status to display: the stored one, or the computed expiry
    status for registers whose status is a function of due_at."""
    if reg.status_source == 'expiry':
        return expiry_status(entry, today)
    return entry.status


# Repeat intervals read from a frequency label, as (days, months). Labels are
# matched lower-cased with dashes as spaces; anything else has no next due.
_INTERVALS = {
    'daily': (1, 0),
    'weekly': (7, 0),
    'fortnightly': (14, 0), 'bi weekly': (14, 0), 'biweekly': (14, 0),
    'monthly': (0, 1),
    'quarterly': (0, 3),
    '6 monthly': (0, 6), 'six monthly': (0, 6), 'half yearly': (0, 6),
    'semi annual': (0, 6), 'semi annually': (0, 6), 'semiannual': (0, 6),
    'biannual': (0, 6), 'bi annual': (0, 6), 'biannually': (0, 6),
    'annual': (0, 12), 'annually': (0, 12), 'yearly': (0, 12),
}


def interval_of(label):
    """(days, months) for a frequency label, or None when it is not one."""
    if not isinstance(label, str):
        return None
    return _INTERVALS.get(re.sub(r'[\s_-]+', ' ', label).strip().lower())


def _is_later(entry, other):
    """Later entry_date wins; on the same date the higher id."""
    return ((entry.entry_date or date.min, entry.id or 0)
            > (other.entry_date or date.min, other.id or 0))


def latest_by_asset(entries):
    """asset_id -> the latest entry for it. Entries with no asset are left out."""
    latest = {}
    for entry in entries:
        if entry.asset_id is None:
            continue
        current = latest.get(entry.asset_id)
        if current is None or _is_later(entry, current):
            latest[entry.asset_id] = entry
    return latest


def next_due(entry, reg):
    """entry_date plus the interval named by the register's interval_field.
    Callers pass only the latest entry per asset; older ones have none."""
    if not reg.interval_field or entry.entry_date is None:
        return None
    step = interval_of((entry.data or {}).get(reg.interval_field))
    if step is None:
        return None
    days, months = step
    return add_months(entry.entry_date, months) + timedelta(days=days)
