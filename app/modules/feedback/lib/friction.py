"""Friction Log rules for the Signal tray."""
from datetime import date, timedelta

from app.modules.core.shared.lib.capabilities import can

# Longest post the Friction Log accepts, in characters.
MAX_LENGTH = 500


def week_start_for(day=None):
    """The Monday of the week `day` falls in; today's Monday when omitted."""
    day = day or date.today()
    return day - timedelta(days=day.weekday())


def can_delete(entry, user):
    """The author deletes their own post; admins delete any."""
    return entry.author_id == user.id or can('manage_feedback', user)
