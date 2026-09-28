"""
The HSE side rail, built from HSE_REGISTERS.

A group with more than one register lists them as sub-pages with open
counts; the group badge is their total. A one-register group is a plain
link. A group with no registers renders as a non-link placeholder.
"""

from flask import url_for

from app.modules.hse.lib.registers import RAIL_GROUPS, registers_in_group


# Rail labels and icons. Icons are SVG path data for the shared rail macro.
GROUP_LABELS = {
    'daily_log': 'Daily log',
    'incidents': 'Incidents',
    'inspections': 'Inspections',
    'compliance': 'Compliance',
    'fleet': 'Fleet',
    'machines': 'Machines',
    'stores': 'Stores',
    'training': 'Training',
}

# Groups that sit between Overview and Calendar; the rest follow Calendar.
TOP_GROUPS = ('daily_log',)

# Calendar is a fixed rail entry, not a RAIL_GROUP.
CALENDAR_ICON = ('M4 6h16v14H4zM4 10h16M8 3v4M16 3v4'
                 'M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01')

OVERVIEW_ICON = 'M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 8h6V4h-6z'

GROUP_ICONS = {
    'daily_log': 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5',
    'incidents': 'M12 3l9 16H3zM12 9v5M12 17.2v.1',
    'inspections': 'M9 4h6v3H9zM5 7h14v13H5zM9 12h6M9 16h4',
    'compliance': 'M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6zM9 12l2 2 4-4',
    'fleet': ('M3 13l2-5h11l3 5v4h-2M3 17v-4M7 17.5a1.6 1.6 0 1 0 3.2 0 1.6 1.6 0 1 0-3.2 0'
              'M15 17.5a1.6 1.6 0 1 0 3.2 0 1.6 1.6 0 1 0-3.2 0'),
    'machines': 'M5 8h14v11H5zM9 8V5h6v3M9 13h6',
    'stores': 'M4 8l8-4 8 4v9l-8 4-8-4zM4 8l8 4 8-4M12 12v9',
    'training': 'M3 8l9-4 9 4-9 4zM7 11v5c0 1.5 2.4 2.6 5 2.6s5-1.1 5-2.6v-5',
}


def _group_item(group, counts):
    registers = registers_in_group(group)
    item = {
        'key': group,
        'label': GROUP_LABELS.get(group, group.title()),
        'icon': GROUP_ICONS.get(group),
        'url': None,
    }
    if registers:
        item['url'] = url_for('hse.register_page',
                              group_key=group, register_key=registers[0].key)
        total = sum(counts.get(r.key, 0) for r in registers)
        if total:
            item['count'] = total
        # Single-register groups get no sub-pages.
        if len(registers) > 1:
            item['children'] = [{
                'key': r.key,
                'label': r.label,
                'url': url_for('hse.register_page', group_key=group, register_key=r.key),
                'count': counts.get(r.key) or None,
            } for r in registers]
    return item


def rail_items(counts=None, active_group=None):
    """Rail items for the shared module_rail macro. `counts` maps a register
    key to its open-item count (open_counts_by_register); a section's badge
    is the total of its registers."""
    counts = counts or {}
    groups = [_group_item(group, counts) for group in RAIL_GROUPS]
    overview = {
        'key': 'overview',
        'label': 'Overview',
        'icon': OVERVIEW_ICON,
        'url': url_for('hse.overview'),
    }
    calendar = {
        'key': 'calendar',
        'label': 'Calendar',
        'icon': CALENDAR_ICON,
        'url': url_for('hse.calendar_month'),
        # Month/Agenda is a toggle on the calendar page, so only Schedule
        # is a separate sub-page.
        'children': [
            {'key': 'calendar', 'label': 'Calendar', 'url': url_for('hse.calendar_month')},
            {'key': 'schedule', 'label': 'Schedule', 'url': url_for('hse.schedule_page')},
        ],
    }
    return ([overview]
            + [g for g in groups if g['key'] in TOP_GROUPS]
            + [calendar]
            + [g for g in groups if g['key'] not in TOP_GROUPS])
