"""The shared dashboard calendar: the event kinds it draws, the month and day
it opens on, and calendar_events_for, which the event sections fill."""
from collections import namedtuple
from datetime import date, datetime

EventKind = namedtuple('EventKind', 'key label')

# Legend order. dashboard.css has a .dash-cal-kind--<key> rule for each; a test checks it.
EVENT_KINDS = (
    EventKind('deadline', 'Deadline'),
    EventKind('install', 'Install'),
    EventKind('removal', 'Removal'),
    EventKind('overdue', 'Overdue'),
    EventKind('site_visit', 'Site visit'),
)


def calendar_events_for(user, start, end):
    """Events on `user`'s calendar from start to end inclusive, scoped by their rail:
    dicts of date, kind (an EVENT_KINDS key), title, url. Event sections add their
    events here; empty when none do."""
    return []


def parse_month(raw, today):
    """?month=YYYY-MM -> (year, month); today's month on anything invalid."""
    try:
        parsed = datetime.strptime(raw or '', '%Y-%m')
    except ValueError:
        return today.year, today.month
    return parsed.year, parsed.month


def parse_day(raw):
    """?day=YYYY-MM-DD -> date, or None on anything invalid."""
    try:
        return date.fromisoformat(raw or '')
    except ValueError:
        return None
