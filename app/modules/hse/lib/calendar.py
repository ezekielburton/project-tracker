"""
The calendar's view model: schedules, entries and expiry dates turned into
days.

Three different things land on the same grid and they are not the same
underneath — a planned occurrence is computed, a logged entry is a row, an
expiry is a date on a row. This module is where they become one shape, so
the templates only loop.

Nothing here writes. The calendar is a view and a way in; the only thing
that ever gets stored is an ordinary HseEntry, filed through the normal
entry form.
"""

from calendar import Calendar
from datetime import date, timedelta

from app.modules.hse.lib.registers import BY_KEY
from app.modules.hse.lib.schedule import coverage, occurrences
from app.modules.hse.lib.schedules import cadence_text


# The five things a day can show. 'planned', 'overdue' and 'done' come from
# schedules; 'logged' is unplanned work; 'expiring' is a due date.
STATES = ('overdue', 'expiring', 'planned', 'logged', 'done')

# Which state colours a day cell when several land on it. Worst wins — the
# same rule the CS calendar uses for risk.
_STATE_RANK = {'overdue': 4, 'expiring': 3, 'planned': 2, 'logged': 1, 'done': 0}

# Twenty-one registers can flood a month, so a cell shows a few and says how
# many more. The drawer has all of them.
MAX_CHIPS_PER_DAY = 3

AGENDA_DAYS = 30

# Monday. The officer's week starts Monday and so does the grid.
FIRST_WEEKDAY = 0

# Keys a view-model dict may not use, because Jinja resolves an attribute
# before a subscript: {{ day.items }} hands the template dict.items, the
# bound method, not the list. It renders as a TypeError three files away
# from the cause. test_hse_calendar.py guards every dict built here.
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
        # The records behind the item. The month cell never touches these;
        # the drawer builds its cards from them.
        'entry': None,
        'schedule': None,
        # Hollow means still to do, filled means settled or shouting. The
        # month grid reads this rather than deciding per state in a
        # template, so a new state cannot quietly render as a hole.
        'filled': state in ('overdue', 'done', 'logged'),
    }
    item.update(extra)
    return item


def occurrence_items(schedules, entries, start, end, today=None):
    """One item per schedule per due date. The per-asset detail rides along
    so the drawer can tick them off without a second pass."""
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
    """Work with no plan behind it — an incident, a near miss, a talk.

    An entry that satisfies an occurrence is skipped: it is already drawn
    inside that occurrence, and showing it twice would double every count
    on the day it was done.
    """
    out = []
    for entry in entries:
        if _is_expiry(entry.register):
            continue                       # drawn on its expiry date instead
        if entry.schedule_id and entry.occurrence_date:
            continue                       # already inside its occurrence
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
    """Certificates, permits, registrations, PPE replacements — drawn on the
    day they run out, from a due date rather than from any schedule."""
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


def items_by_day(schedules, entries, start, end, today=None, state=None):
    """Everything on the grid, keyed by date. `state` narrows to one of
    STATES; an unknown value is ignored rather than emptying the page."""
    items = (occurrence_items(schedules, entries, start, end, today)
             + logged_items(entries, start, end)
             + expiry_items(entries, start, end))

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
    """The first and last day the month grid actually renders — the weeks
    overhang the month at both ends, and work shown there must be loaded."""
    weeks = Calendar(firstweekday=FIRST_WEEKDAY).monthdatescalendar(year, month)
    return weeks[0][0], weeks[-1][-1]


def month_grid(grouped, year, month, today):
    """Weeks of days, Monday first, each carrying its items and the worst
    state on it."""
    weeks = []
    for week in Calendar(firstweekday=FIRST_WEEKDAY).monthdatescalendar(year, month):
        days = []
        for day in week:
            items = grouped.get(day, [])
            worst = items[0]['state'] if items else None
            days.append({
                'date': day,
                'in_month': day.month == month,
                'is_today': day == today,
                # Not 'items' — see _SHADOWED_KEYS.
                'day_items': items,
                'shown': items[:MAX_CHIPS_PER_DAY],
                'more': max(0, len(items) - MAX_CHIPS_PER_DAY),
                'count': len(items),
                'worst': worst,
            })
        weeks.append(days)
    return weeks


def agenda_groups(grouped, today, days_ahead=AGENDA_DAYS):
    """Days with something on them, from today forward. Empty days are left
    out — an agenda is a list of what is coming, not a second grid."""
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
            # The agenda renders the same cards the drawer does, so a day
            # cannot read one way in one view and another way in the other.
            'cards': cards,
            'summary': day_summary(cards),
            'count': len(items),
            'overdue': sum(1 for c in cards if c['state'] == 'overdue'),
        })
    return out


def _short(day):
    """5 Sep. Not strftime('%-d %b') — that flag does not exist on Windows,
    and this runs on his machine."""
    return f'{day.day} {day:%b}'


def _logged_meta(entry):
    """Who filed it and when, from created_at rather than entry_date: the
    officer wants to know when it was written down, not the day it covers."""
    who = getattr(getattr(entry, 'created_by', None), 'name', None)
    when = getattr(entry, 'created_at', None)
    if when and who:
        return f'Logged {when:%H:%M} by {who}'
    if who:
        return f'Logged by {who}'
    return 'Logged'


def _target_card(item, target, today):
    """One asset on one occurrence — the unit the officer actually acts on.

    The drawer is flat on purpose: a card per thing to do, rather than a
    schedule with its assets nested underneath. Every line is then one
    action, and how late it is sits next to it.
    """
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


def _entry_card(item, today):
    """Work with no occurrence behind it — something logged, or something
    running out."""
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
        # A logged entry's label IS its register, so repeating it underneath
        # printed the same words twice.
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
    """A day, flattened into one card per thing.

    An occurrence covering six vehicles becomes six cards, because six
    vehicles is six jobs. Anything already done keeps its place in the list
    rather than disappearing — he should be able to see what he has done
    today, not only what is left.
    """
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
    """"3 due · 1 done · 1 overdue" — the line under the drawer's date.

    Due counts what is still outstanding, so due and done never double-count
    the same card.
    """
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
    """The header counts.

    Due, done and overdue come straight from coverage() — the same function
    the performance page reads — so the calendar header and the performance
    page can never disagree about what a month looked like.
    """
    cov = coverage(schedules, entries, month_start, month_end, today)
    return {
        'due': cov['due'],
        'done': cov['done'],
        'overdue': cov['outstanding'],
        # None when nothing was due. Rendered as an em dash, never as 0%.
        'percent': cov['percent'],
        # Work he did that nobody planned — incidents, near misses, talks.
        # It sits beside coverage on purpose: a low percentage next to a
        # high unplanned count is a month that went sideways, not a month
        # of neglect, and the tile row should let a manager see that.
        'unplanned': len(logged_items(entries, month_start, month_end)),
    }


STATE_LABELS = {'overdue': 'Overdue', 'expiring': 'Expiring',
                'planned': 'Planned', 'logged': 'Logged', 'done': 'Done'}

# The legend reads in the order work moves through, not in the worst-first
# order the grid sorts by: planned, then done, then the two that need him.
LEGEND_ORDER = ('planned', 'done', 'overdue', 'expiring', 'logged')


def state_chips(grouped_all, active_state):
    """The legend, which doubles as the filter: clicking a state narrows to
    it, clicking it again clears. Counted over everything in view, and every
    state renders even at zero so the row does not jump about.

    `filled` matches the month grid, so the legend reads as a key to it.
    """
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
        # Clicking the state already showing clears the filter, so the
        # legend needs no separate "All".
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
