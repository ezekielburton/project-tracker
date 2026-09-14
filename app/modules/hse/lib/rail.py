"""
The HSE rail — built from HSE_REGISTERS, so it grows as registers are
declared rather than being a second list to keep in sync.

A group with no declared register renders as a non-link placeholder: the
officer can see what is coming without a dead link to click.
"""

from flask import url_for

from app.modules.hse.lib.registers import RAIL_GROUPS, registers_in_group


# Rail labels and icons, in rail order. Icons are SVG path data — the
# shared rail renders whatever path it is handed, so the icons stay this
# module's own.
GROUP_LABELS = {
    'incidents': 'Incidents',
    'inspections': 'Inspections',
    'compliance': 'Compliance',
    'fleet': 'Fleet',
    'machines': 'Machines',
    'stores': 'Stores',
    'training': 'Training',
}

# The calendar sits above the registers: it is where his week starts, not a
# register. Its own entry rather than a RAIL_GROUP, because no register
# lives behind it.
CALENDAR_ICON = ('M4 6h16v14H4zM4 10h16M8 3v4M16 3v4'
                 'M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01')

OVERVIEW_ICON = 'M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 8h6V4h-6z'

GROUP_ICONS = {
    'incidents': 'M12 3l9 16H3zM12 9v5M12 17.2v.1',
    'inspections': 'M9 4h6v3H9zM5 7h14v13H5zM9 12h6M9 16h4',
    'compliance': 'M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6zM9 12l2 2 4-4',
    'fleet': ('M3 13l2-5h11l3 5v4h-2M3 17v-4M7 17.5a1.6 1.6 0 1 0 3.2 0 1.6 1.6 0 1 0-3.2 0'
              'M15 17.5a1.6 1.6 0 1 0 3.2 0 1.6 1.6 0 1 0-3.2 0'),
    'machines': 'M5 8h14v11H5zM9 8V5h6v3M9 13h6',
    'stores': 'M4 8l8-4 8 4v9l-8 4-8-4zM4 8l8 4 8-4M12 12v9',
    'training': 'M3 8l9-4 9 4-9 4zM7 11v5c0 1.5 2.4 2.6 5 2.6s5-1.1 5-2.6v-5',
}


def rail_items(counts=None, active_group=None):
    """Rail items for the shared module_rail macro. `counts` maps a group
    key to its open-item count; a group with no count shows no badge."""
    counts = counts or {}
    items = [{
        'key': 'overview',
        'label': 'Overview',
        'icon': OVERVIEW_ICON,
        'url': url_for('hse.overview'),
    }, {
        'key': 'calendar',
        'label': 'Calendar',
        'icon': CALENDAR_ICON,
        'url': url_for('hse.calendar_month'),
    }]
    for group in RAIL_GROUPS:
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
            count = counts.get(group)
            if count:
                item['count'] = count
        items.append(item)
    return items
