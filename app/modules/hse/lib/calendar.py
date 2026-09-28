"""
The calendar's view model (Month and Agenda views).

Computed schedule occurrences, logged entries and expiry dates are turned
into one item shape, grouped by day, so templates only loop. Read-only:
work is stored as an ordinary HseEntry through the normal entry form.
"""

from calendar import Calendar
from datetime import date, timedelta

from app.modules.hse.lib.computed import latest_by_asset, next_due
from app.modules.hse.lib.registers import BY_KEY, counts_as_done, interval_registers
from app.modules.hse.lib.schedule import coverage, occurrences
from app.modules.hse.lib.schedules import cadence_text


# The five things a day can show. 'planned', 'overdue' and 'done' come from
# schedules; 'logged' is unplanned work; 'expiring' is a due date (a PM due
# date turns 'overdue' once it has passed).
STATES = ('overdue', 'expiring', 'planned', 'logged', 'done')

# Sort rank; the worst state on a day colours its cell.
_STATE_RANK = {'overdue': 4, 'expiring': 3, 'planned': 2, 'logged': 1, 'done': 0}

# Chips per month cell; the rest show as "+N more" and are listed in the drawer.
MAX_CHIPS_PER_DAY = 3

AGENDA_DAYS = 30

# Weeks start on Monday.
FIRST_WEEKDAY = 0

# Keys a view-model dict must not use: Jinja resolves attributes before
# subscripts, so {{ day.items }} returns the dict.items method, not the list.
# test_hse_calendar.py checks every dict built here.
_SHADOWED_KEYS = frozenset(dir({}))


def _is_expiry(register_key):
    reg = BY_KEY.get(register_key)
    return reg is not None and reg.status_source == 'expiry'


def _register_label(register_key):
    reg = BY_KEY.get(register_key)
    return reg.label if reg else register_key


def _item(state, day, label, detail=None, **extra):
    item = {
        'state': state,
        'date': day,
        'label': label,
        'detail': detail,
        'register': None,
        'register_label': None,
        'schedule_id': None,
        'entry_id': None,
        'ref': None,
        'targets': (),
        'done': None,
        'due': None,
        # Source records; the drawer builds its cards from these.
        'entry': None,
        'schedule': None,
        # Hollow = still to do; filled = settled or urgent. Set here so
        # templates never decide it per state.
        'filled': state in ('overdue', 'done', 'logged'),
    }
    item.update(extra)
    return item


def occurrence_items(schedules, entries, start, end, today=None):
    """One item per schedule per due date, carrying its per-asset targets
    for the drawer."""
    out = []
    for occ in occurrences(schedules, entries, start, end, today):
        out.append(_item(
            occ['state'], occ['date'], occ['label'],
            detail=(f"{occ['done']} of {occ['due']}" if occ['due'] > 1 else None),
            register=occ['register'],
            register_label=_register_label(occ['register']),
            schedule_id=occ['schedule_id'],
            schedule=occ['schedule'],
            targets=tuple(occ['items']),
            done=occ['done'],
            due=occ['due'],
        ))
    return out


def logged_items(entries, start, end):
    """Unplanned work (incidents, near misses, talks). Entries that satisfy
    an occurrence are skipped; they are already counted inside it."""
    out = []
    for entry in entries:
        if _is_expiry(entry.register):
            continue                       # drawn on its expiry date instead
        if entry.schedule_id and entry.occurrence_date:
            continue                       # already inside its occurrence
        if not counts_as_done(entry):
            continue                       # not held (yet): not logged work
        if entry.entry_date is None or not (start <= entry.entry_date <= end):
            continue
        out.append(_item(
            'logged', entry.entry_date, _register_label(entry.register),
            detail=entry.ref,
            register=entry.register,
            register_label=_register_label(entry.register),
            entry_id=entry.id,
            ref=entry.ref,
            entry=entry,
        ))
    return out


def expiry_items(entries, start, end):
    """Entries in expiry registers (certificates, permits, PPE), placed on
    their due date."""
    out = []
    for entry in entries:
        if not _is_expiry(entry.register) or entry.due_at is None:
            continue
        if not (start <= entry.due_at <= end):
            continue
        label = (getattr(entry, 'compliance_item', None) and entry.compliance_item.label) or _register_label(entry.register)
        if entry.asset is not None:
            label = f'{label} — {entry.asset.label}'
        out.append(_item(
            'expiring', entry.due_at, label,
            detail=entry.ref,
            register=entry.register,
            register_label=_register_label(entry.register),
            entry_id=entry.id,
            ref=entry.ref,
            entry=entry,
        ))
    return out


def pm_due_items(entries, start, end, today=None):
    """Each machine's next preventive maintenance, from its latest entry
    only. `entries` must hold every entry in those registers, not just the
    window's, or an older entry would pass for the latest."""
    today = today or date.today()
    out = []
    for reg in interval_registers():
        latest = latest_by_asset(e for e in entries if e.register == reg.key)
        for entry in latest.values():
            due = next_due(entry, reg)
            if due is None or not (start <= due <= end):
                continue
            asset = getattr(entry, 'asset', None)
            out.append(_item(
                'overdue' if due < today else 'expiring', due,
                f'PM · {asset.label}' if asset is not None else 'PM due',
                detail=entry.ref,
                register=reg.key,
                register_label=reg.label,
                ref=entry.ref,
                entry=entry,
                kind='pm_due',
                asset_id=entry.asset_id,
            ))
    return out


def items_by_day(schedules, entries, start, end, today=None, state=None):
    """Everything on the grid, keyed by date. `state` narrows to one of
    STATES; an unknown value is ignored."""
    items = (occurrence_items(schedules, entries, start, end, today)
             + logged_items(entries, start, end)
             + expiry_items(entries, start, end)
             + pm_due_items(entries, start, end, today))

    if state in STATES:
        items = [i for i in items if i['state'] == state]

    grouped = {}
    for item in items:
        grouped.setdefault(item['date'], []).append(item)
    for day in grouped:
        grouped[day].sort(key=lambda i: (-_STATE_RANK.get(i['state'], 0),
                                         i['label'] or ''))
    return grouped


def grid_bounds(year, month):
    """First and last day the month grid renders, including the overhang
    weeks, so work shown there gets loaded."""
    weeks = Calendar(firstweekday=FIRST_WEEKDAY).monthdatescalendar(year, month)
    return weeks[0][0], weeks[-1][-1]


def _is_daily(item):
    schedule = item.get('schedule')
    return schedule is not None and getattr(schedule, 'frequency', None) == 'daily'


def _cell_chips(items):
    """Chips a month cell shows, and how many are left for the drawer.
    One-off items go first; two or more daily items fold into one line
    coloured by the worst of them."""
    daily = [i for i in items if _is_daily(i)]
    others = [i for i in items if not _is_daily(i)]
    if len(daily) > 1:
        # items arrive worst-first, so the first daily item is the worst.
        daily = [_item(daily[0]['state'], daily[0]['date'],
                       f'Daily checks · {len(daily)}')]
    room = MAX_CHIPS_PER_DAY - len(daily)
    return others[:room] + daily, max(0, len(others) - room)


def month_grid(grouped, year, month, today):
    """Weeks of days, Monday first, each carrying its items and the worst
    state on it."""
    weeks = []
    for week in Calendar(firstweekday=FIRST_WEEKDAY).monthdatescalendar(year, month):
        days = []
        for day in week:
            items = grouped.get(day, [])
            worst = items[0]['state'] if items else None
            shown, more = _cell_chips(items)
            days.append({
                'date': day,
                'in_month': day.month == month,
                'is_today': day == today,
                # Not 'items' — see _SHADOWED_KEYS.
                'day_items': items,
                'shown': shown,
                'more': more,
                'count': len(items),
                'worst': worst,
            })
        weeks.append(days)
    return weeks


def agenda_groups(grouped, today, days_ahead=AGENDA_DAYS):
    """Days with items, from today to `days_ahead` out. Empty days are
    skipped."""
    horizon = today + timedelta(days=days_ahead)
    out = []
    for day in sorted(grouped):
        if not (today <= day <= horizon):
            continue
        items = grouped[day]
        if not items:
            continue
        cards = drawer_cards(items, today)
        out.append({
            'date': day,
            'day_items': items,
            # Same cards as the drawer, so both views read the same.
            'cards': cards,
            'summary': day_summary(cards),
            'count': len(items),
            'overdue': sum(1 for c in cards if c['state'] == 'overdue'),
        })
    return out


def _short(day):
    """'5 Sep'. Avoids strftime('%-d'), which fails on Windows."""
    return f'{day.day} {day:%b}'


def _logged_meta(entry):
    """'Logged HH:MM by <name>'. The time is the entry's own Time field when
    set, else when it was filed (created_at)."""
    who = getattr(getattr(entry, 'created_by', None), 'name', None)
    created = getattr(entry, 'created_at', None)
    when = (getattr(entry, 'data', None) or {}).get('entry_time') or (
        f'{created:%H:%M}' if created else None)
    if when and who:
        return f'Logged {when} by {who}'
    if who:
        return f'Logged by {who}'
    return 'Logged'


def _target_card(item, target, today):
    """Card for one asset on one occurrence: a single action and how late
    it is."""
    asset, entry = target['asset'], target['entry']
    day = item['date']

    if target['done']:
        state, meta = 'done', _logged_meta(entry) if entry is not None else 'Done'
    elif day < today:
        days = (today - day).days
        state = 'overdue'
        meta = f"Was due {_short(day)} · {days} day{'' if days == 1 else 's'} overdue"
    else:
        state = 'planned'
        cadence = cadence_text(item['schedule']) if item['schedule'] is not None else ''
        meta = f'{cadence} · due today' if day == today else cadence

    return {
        'state': state,
        'title': asset.label if asset is not None else item['label'],
        'subtitle': item['register_label'],
        'meta': meta,
        'done': target['done'],
        'entry_id': entry.id if entry is not None else None,
        'ref': entry.ref if entry is not None else None,
        # What "Log it" needs to open a prefilled form.
        'register': item['register'],
        'schedule_id': item['schedule_id'],
        'asset_id': asset.id if asset is not None else None,
        'date': day,
    }


def _pm_card(item, today):
    """Card for a machine's PM due date. "Log it" files the next PM for
    that machine, which moves the due date on."""
    day = item['date']
    left = (day - today).days
    if left < 0:
        meta = f"Was due {_short(day)} · {-left} day{'' if left == -1 else 's'} overdue"
    elif left == 0:
        meta = 'Due today'
    else:
        meta = f"Due {_short(day)} · {left} day{'' if left == 1 else 's'} left"
    return {
        'state': item['state'],
        'title': item['label'],
        'subtitle': item['register_label'],
        'meta': f"{meta} · last {item['ref']}",
        'done': False,
        'entry_id': None,
        'ref': item['ref'],
        'register': item['register'],
        'schedule_id': None,
        'asset_id': item['asset_id'],
        # "Log it" dates the new PM today: it is done when it is logged.
        'date': today,
    }


def _entry_card(item, today):
    """Card for a logged or expiring entry (no occurrence behind it)."""
    if item.get('kind') == 'pm_due':
        return _pm_card(item, today)
    entry = item['entry']
    if item['state'] == 'expiring':
        left = (item['date'] - today).days
        if left < 0:
            meta = f'Expired {_short(item["date"])}'
        elif left == 0:
            meta = 'Expires today'
        else:
            meta = f"Expires {_short(item['date'])} · {left} day{'' if left == 1 else 's'} left"
    else:
        meta = _logged_meta(entry) if entry is not None else ''

    return {
        'state': item['state'],
        'title': item['label'],
        # A logged entry's label is its register name; don't repeat it.
        'subtitle': (None if item['label'] == item['register_label']
                     else item['register_label']),
        'meta': meta,
        'done': item['state'] == 'logged',
        'entry_id': item['entry_id'],
        'ref': item['ref'],
        'register': item['register'],
        'schedule_id': None,
        'asset_id': None,
        'date': item['date'],
    }


def drawer_cards(day_items, today=None):
    """A day flattened into one card per job (an occurrence covering six
    vehicles gives six cards), worst first. Done cards stay in the list."""
    today = today or date.today()
    cards = []
    for item in day_items:
        if item['targets']:
            cards.extend(_target_card(item, t, today) for t in item['targets'])
        else:
            cards.append(_entry_card(item, today))
    cards.sort(key=lambda c: (-_STATE_RANK.get(c['state'], 0), c['title'] or ''))
    return cards


def day_summary(cards):
    """"3 due · 1 done · 1 overdue", shown under the drawer's date. Due
    counts outstanding cards only, so it never overlaps done."""
    parts = []
    due = sum(1 for c in cards if c['state'] in ('planned', 'overdue', 'expiring'))
    done = sum(1 for c in cards if c['state'] == 'done')
    overdue = sum(1 for c in cards if c['state'] == 'overdue')
    if due:
        parts.append(f'{due} due')
    if done:
        parts.append(f'{done} done')
    if overdue:
        parts.append(f'{overdue} overdue')
    return ' · '.join(parts)


def kpis(schedules, entries, month_start, month_end, today=None):
    """Header counts. Due, done and overdue come from coverage(), the same
    source as the performance page, so the two always agree."""
    cov = coverage(schedules, entries, month_start, month_end, today)
    return {
        'due': cov['due'],
        'done': cov['done'],
        'overdue': cov['outstanding'],
        # None when nothing was due; rendered as an em dash, never 0%.
        'percent': cov['percent'],
        # Unplanned logged work, shown beside coverage so a low percentage
        # can be read in context.
        'unplanned': len(logged_items(entries, month_start, month_end)),
    }


STATE_LABELS = {'overdue': 'Overdue', 'expiring': 'Expiring',
                'planned': 'Planned', 'logged': 'Logged', 'done': 'Done'}

# Legend follows workflow order, not the grid's worst-first sort.
LEGEND_ORDER = ('planned', 'done', 'overdue', 'expiring', 'logged')


def state_chips(grouped_all, active_state):
    """The legend, which is also the state filter (click to narrow, click
    again to clear). Counts cover everything in view; every state shows,
    even at zero. `filled` matches the month grid."""
    counts = {}
    total = 0
    for items in grouped_all.values():
        for item in items:
            counts[item['state']] = counts.get(item['state'], 0) + 1
            total += 1
    return [{
        'label': STATE_LABELS[s],
        'value': s,
        'count': counts.get(s, 0),
        'filled': s in ('overdue', 'done', 'logged'),
        # Clicking the active state clears the filter; no separate "All".
        'href_state': None if s == active_state else s,
        'active': s == active_state,
    } for s in LEGEND_ORDER]


def shadowed_keys(mapping):
    """Keys in a view model that Jinja would resolve to a dict method
    instead of the value. Empty is the only acceptable answer."""
    return sorted(k for k in mapping if k in _SHADOWED_KEYS)


def shift_month(year, month, delta):
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def parse_month(raw, today=None):
    """?month=YYYY-MM -> (year, month); this month on anything invalid."""
    today = today or date.today()
    if raw:
        try:
            y, m = raw.split('-')
            y, m = int(y), int(m)
            if 1 <= m <= 12:
                return y, m
        except (AttributeError, ValueError):
            pass
    return today.year, today.month


def parse_day(raw):
    try:
        return date.fromisoformat((raw or '').strip())
    except (AttributeError, TypeError, ValueError):
        return None


def default_day(weeks, today):
    """Which day the drawer opens on: today if it has anything, else the
    first day in the month that does."""
    for week in weeks:
        for day in week:
            if day['is_today'] and day['day_items']:
                return day['date']
    for week in weeks:
        for day in week:
            if day['in_month'] and day['day_items']:
                return day['date']
    return None
