"""A month as weeks of days, Monday first, for the calendar pages."""
from calendar import Calendar

_CALENDAR = Calendar(firstweekday=0)


def month_span(year, month):
    """(first, last) date drawn for the month, padding weeks included."""
    weeks = _CALENDAR.monthdatescalendar(year, month)
    return weeks[0][0], weeks[-1][-1]


def month_weeks(year, month, today, by_day=None):
    """Weeks of days: date, in_month, is_today, events, count. `by_day` maps a date to its events.
    The key is 'events', not 'items': Jinja would read day.items as the dict method."""
    by_day = by_day or {}
    return [[{
        'date': day,
        'in_month': day.month == month,
        'is_today': day == today,
        'events': by_day.get(day, []),
        'count': len(by_day.get(day, [])),
    } for day in week] for week in _CALENDAR.monthdatescalendar(year, month)]
