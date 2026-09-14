"""
Every derived value in the module, computed at read time.

The source spreadsheet stores these as formulas, which is exactly why
several of its columns disagree with their own data. Nothing in this
module writes a derived value to the database.
"""

from datetime import date


# Days before expiry at which a compliance item reads "Expiring soon" —
# the workbook's own threshold.
EXPIRING_SOON_DAYS = 30

# Severity ranking, used for sorting and for the workbook's severity score.
SEVERITY_SCORE = {'Low': 1, 'Medium': 2, 'High': 3, 'Critical': 4}

# Days an action of each severity may stay open before it is late.
# Agreed with the officer, 14 Sep 2026.
SLA_DAYS = {'Critical': 4, 'High': 7, 'Medium': 15, 'Low': 30}


def _today(today=None):
    return today or date.today()


def days_open(entry, today=None):
    """Days the entry has been open. Counts to today while open, and
    freezes at the closing date once closed. None without a date."""
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
    """Valid / Expiring soon / Expired, from due_at alone. This is the
    status for registers declaring status_source='expiry'."""
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
    """Days open that were his — total open, less the time parked with
    someone else. This is what the performance page measures."""
    total = days_open(entry, today)
    if total is None:
        return None
    return max(0, total - days_waiting(entry, today))


def sla_days(entry):
    """The SLA for this entry's severity, or None when severity is unset."""
    return SLA_DAYS.get(entry.severity)


def closed_on_time(entry, today=None):
    """True when a closed entry met its SLA. The clock excludes time
    parked with someone else, so another person's delay is not his.
    None for an open entry or one with no severity."""
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
