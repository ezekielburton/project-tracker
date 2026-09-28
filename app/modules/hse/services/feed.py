"""
The sanctioned way for other modules to read HSE numbers; they must not
query this module's models directly. No callers yet.
"""

from datetime import date

from app.modules.hse.models import HseEntry


def open_count(today=None):
    """Entries still open across every register."""
    return HseEntry.query.filter(HseEntry.closed_at.is_(None)).count()


def overdue_count(today=None):
    """Entries past their due date and not closed."""
    cutoff = today or date.today()
    return (HseEntry.query
            .filter(HseEntry.closed_at.is_(None))
            .filter(HseEntry.due_at.isnot(None))
            .filter(HseEntry.due_at < cutoff)
            .count())
