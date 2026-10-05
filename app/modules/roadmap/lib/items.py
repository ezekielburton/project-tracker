"""The roadmap's items, set by hand until the Digital Innovation module drives
them. Company-facing: no version numbers, no internal-only work.

Each item is a name, a status, and for anything not live a month, a delivery
label and a one-line note. `due` only feeds the in-progress countdown.
"""
from datetime import date, datetime, time

LIVE = 'live'
IN_PROGRESS = 'in_progress'
COMING = 'coming'

UPDATED = date(2026, 10, 2)

# Deliveries count down to the end of the due day, Dubai time.
DEADLINE_TIME = time(23, 59, 59)
UTC_OFFSET = '+04:00'

# (key, filter label, heading), in display order.
MONTHS = [
    ('oct', 'Oct', 'October'),
    ('nov', 'Nov', 'November'),
    ('dec', 'Dec', 'December'),
    ('jan', 'Jan', 'January 2027'),
    ('feb', 'Feb', 'February 2027'),
    ('later', 'Later', 'Later'),
]

ITEMS = [
    {'name': 'Projects', 'status': LIVE},
    {'name': 'Client Servicing', 'status': LIVE},
    {'name': 'Chat & Signal', 'status': LIVE},
    {'name': 'Help & Wiki', 'status': LIVE},
    {'name': 'Digital Innovation board', 'status': LIVE},

    {'name': 'Dashboards', 'month': 'oct', 'label': '8 Oct', 'due': date(2026, 10, 8), 'status': IN_PROGRESS,
     'note': 'Your own home page showing what needs you today, with My hub for leave and sick days.'},
    {'name': 'HR', 'month': 'oct', 'label': '16 Oct', 'due': date(2026, 10, 16), 'status': COMING,
     'note': 'Leave, sick days and reimbursements requested and approved in OVP.'},
    {'name': 'Production', 'month': 'oct', 'label': '31 Oct', 'due': date(2026, 10, 31), 'status': COMING,
     'note': 'Production picks up jobs when design is done, with materials, stock and quality checks.'},

    {'name': 'Logistics', 'month': 'nov', 'label': 'Mid Nov', 'status': COMING,
     'note': 'Deliveries, installs and removals, planned with the team.'},
    {'name': 'Optimisation pass', 'month': 'nov', 'label': 'Late Nov', 'status': COMING,
     'note': 'Time set aside to make OVP faster and more reliable before new features start.'},
    {'name': 'UI cleanup pass', 'month': 'nov', 'label': 'Late Nov', 'status': COMING,
     'note': 'Every page tidied to one consistent style. Same colours, nothing to relearn.'},

    {'name': 'Colour directory', 'month': 'dec', 'status': COMING,
     'note': 'Client colours and Pantones in one place.'},
    {'name': 'Design file templates', 'month': 'dec', 'status': COMING,
     'note': 'The template library, brought up to date.'},
    {'name': 'Notifications', 'month': 'dec', 'status': COMING,
     'note': 'Clearer notifications, and you choose what you get.'},
    {'name': 'Designer work calendar', 'month': 'dec', 'status': COMING,
     'note': 'Hours and time booked against projects.'},
    {'name': 'Client feedback forms', 'month': 'dec', 'status': COMING,
     'note': 'Send feedback forms to clients and see the results.'},
    {'name': 'Beauty event tool', 'month': 'dec', 'status': COMING,
     'note': 'Planning and running beauty events.'},
    {'name': 'Financial planning', 'month': 'jan', 'status': COMING,
     'note': 'Forecasts built from live jobs, planned with finance.'},
    {'name': 'OVP app for phone and desktop', 'month': 'feb', 'status': COMING,
     'note': 'OVP as an app, with notifications on your phone.'},
    {'name': 'Client briefs straight into OVP', 'month': 'later', 'status': COMING,
     'note': 'Briefs sent by email land in OVP directly.'},
]


def roadmap_view(today):
    """Everything the page renders: live names, the item in progress with days
    left, and the rest grouped by month in MONTHS order (empty months dropped)."""
    upcoming = [item for item in ITEMS if item['status'] != LIVE]
    current = next((item for item in upcoming if item['status'] == IN_PROGRESS), None)
    days_left = (current['due'] - today).days if current and current.get('due') else None
    deadline = (datetime.combine(current['due'], DEADLINE_TIME).isoformat() + UTC_OFFSET
                if current and current.get('due') else None)
    groups = [
        {'key': key, 'short': short, 'title': title,
         'entries': [item for item in upcoming if item['month'] == key]}
        for key, short, title in MONTHS
    ]
    return {
        'updated': UPDATED,
        'live': [item['name'] for item in ITEMS if item['status'] == LIVE],
        'current': current,
        'days_left': days_left,
        'deadline': deadline,
        'groups': [group for group in groups if group['entries']],
    }
