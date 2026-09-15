"""
The Schedule tab's own logic: what a recurring obligation may say, and how
it reads on the page.

Validation here is deliberately pure — no database, no mapped model — so
every rule can be tested without the app, and so the same code can preview
dates for a form that has not been saved yet.

Nothing in this module writes. Occurrences come from lib/schedule.py and
are computed at read time; this file only decides what a schedule is
allowed to be.
"""

from collections import namedtuple
from datetime import date, timedelta

from app.modules.hse.lib.registers import asset_field, register, schedulable_registers
from app.modules.hse.lib.schedule import (
    FREQUENCIES, next_due, occurrence_dates, occurrences,
)


MAX_LABEL = 200
MAX_INTERVAL = 99

# How many dates the form shows back, and how far ahead it will look to
# find them — three years covers an annual schedule with an interval.
PREVIEW_COUNT = 5
PREVIEW_HORIZON_DAYS = 366 * 3

WEEKDAYS = ((0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
            (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'))

FREQUENCY_LABELS = (('daily', 'Daily'), ('weekly', 'Weekly'),
                    ('monthly', 'Monthly'), ('quarterly', 'Quarterly'),
                    ('annual', 'Annual'))

# The frequencies that take a day of the month rather than a weekday.
MONTHLY_FREQUENCIES = ('monthly', 'quarterly', 'annual')

_ORDINAL_LAST = {1: 'st', 2: 'nd', 3: 'rd'}

WEEKDAY_SHORT = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')

ASSET_PLURALS = {'vehicle': 'vehicles', 'machine': 'machines',
                 'forklift': 'forklifts', 'area': 'areas'}

# How far back the table looks for work he still owes. Long enough to catch
# a missed monthly, short enough that a schedule abandoned last year does
# not permanently read as overdue.
LOOKBACK_DAYS = 120


# A saved schedule and an unsaved form both need to generate dates, and the
# engine only reads attributes — so a plain record stands in for the model.
Plan = namedtuple(
    'Plan', 'frequency interval weekday day_of_month starts_on ends_on active assets id')
Plan.__new__.__defaults__ = (True, (), None)


class ValidationError(Exception):
    """Carries a field -> message map straight back to the form."""

    def __init__(self, errors):
        super().__init__('invalid schedule')
        self.errors = errors


def _parse_date(raw):
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat((raw or '').strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _parse_int(raw):
    try:
        return int(str(raw).strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        return f'{n}th'
    return f'{n}{_ORDINAL_LAST.get(n % 10, "th")}'


def cadence_text(schedule):
    """How often, in the words the officer would use. Read off the same
    fields the generator uses, so the sentence cannot drift from the dates."""
    freq = schedule.frequency
    every = max(1, schedule.interval or 1)

    if freq == 'daily':
        return 'Every day' if every == 1 else f'Every {every} days'

    if freq == 'weekly':
        weekday = schedule.weekday
        if weekday is None and schedule.starts_on is not None:
            weekday = schedule.starts_on.weekday()
        day = dict(WEEKDAYS).get(weekday, '')
        if every == 1:
            return f'Every {day}'.strip()
        return f'Every {every} weeks{" on " + day if day else ""}'

    if freq in MONTHLY_FREQUENCIES:
        day = schedule.day_of_month
        if day is None and schedule.starts_on is not None:
            day = schedule.starts_on.day
        on = f' on the {_ordinal(day)}' if day else ''
        if freq == 'monthly':
            head = 'Every month' if every == 1 else f'Every {every} months'
        elif freq == 'quarterly':
            head = 'Every quarter' if every == 1 else f'Every {every} quarters'
        else:
            head = 'Every year' if every == 1 else f'Every {every} years'
        return head + on

    return freq or '—'


def cadence_short(schedule):
    """The compact form for the table — "Weekly · Mon", "Every 6 months ·
    5th". cadence_text() stays the sentence form the calendar cards use;
    both read the same fields as the generator, so neither can drift from
    the dates."""
    freq = schedule.frequency
    every = max(1, schedule.interval or 1)

    if freq == 'daily':
        return 'Daily' if every == 1 else f'Every {every} days'

    if freq == 'weekly':
        weekday = schedule.weekday
        if weekday is None and schedule.starts_on is not None:
            weekday = schedule.starts_on.weekday()
        day = WEEKDAY_SHORT[weekday] if weekday is not None and 0 <= weekday <= 6 else ''
        head = 'Weekly' if every == 1 else f'Every {every} weeks'
        return f'{head} · {day}' if day else head

    if freq in MONTHLY_FREQUENCIES:
        day = schedule.day_of_month
        if day is None and schedule.starts_on is not None:
            day = schedule.starts_on.day
        on = f' · {_ordinal(day)}' if day else ''
        if freq == 'monthly':
            head = 'Monthly' if every == 1 else f'Every {every} months'
        elif freq == 'quarterly':
            head = 'Quarterly' if every == 1 else f'Every {every} quarters'
        else:
            head = 'Annual' if every == 1 else f'Every {every} years'
        return head + on

    return freq or '—'


def applies_to_text(schedule):
    """What the schedule covers, in a few words.

    A list of every plate is unreadable at four vehicles and useless at
    twelve, so anything past two collapses to a count of its kind. The
    full list is still in the form.
    """
    declared = list(schedule.assets or [])
    if not declared:
        return 'Site-wide'

    active = [a for a in declared if getattr(a, 'active', True)]
    if not active:
        # Every asset retired: the schedule is due for nothing, and saying
        # so is better than naming things that no longer exist.
        return 'Nothing active'
    if len(active) <= 2:
        return ', '.join(a.ref or a.label for a in active)

    kinds = {getattr(a, 'kind', None) for a in active}
    if len(kinds) == 1:
        return f'{len(active)} {ASSET_PLURALS.get(next(iter(kinds)), "assets")}'
    return f'{len(active)} assets'


def due_status(schedule, entries=(), today=None, lookback_days=LOOKBACK_DAYS):
    """The date this schedule is actually waiting on, and how it reads.

    Not simply the next future occurrence. If Monday's inspection was never
    done then Monday is what he owes, and showing next Monday instead would
    hide it behind a date that looks fine. The oldest outstanding occurrence
    wins; only when nothing is outstanding does the next one show.
    """
    today = today or date.today()
    if not getattr(schedule, 'active', True):
        return {'date': None, 'label': None, 'overdue_days': 0}

    # occurrences() comes back in date order, so the first overdue one is
    # the oldest thing he still owes.
    window_start = today - timedelta(days=lookback_days)
    for occ in occurrences([schedule], entries, window_start, today, today):
        if occ['state'] == 'overdue':
            days = (today - occ['date']).days
            return {'date': occ['date'], 'label': f'{days}d overdue',
                    'overdue_days': days}

    upcoming = next_due(schedule, today)
    if upcoming is None:
        return {'date': None, 'label': None, 'overdue_days': 0}
    ahead = (upcoming - today).days
    return {'date': upcoming,
            'label': 'Today' if ahead == 0 else f'{ahead}d',
            'overdue_days': 0}


def clean_payload(payload, available_asset_ids=(), check_assets=True):
    """Turn a submitted form into the values a schedule may hold.

    Raises ValidationError with a field -> message map. Returns
    (values, asset_ids); `values` maps one-to-one onto HseSchedule columns.

    `check_assets=False` skips the asset rules only — the preview uses it,
    because which assets are picked never changes the dates, and refusing
    to show them until the asset list is right would hide the one thing
    the preview exists to catch.
    """
    errors = {}
    payload = payload or {}

    label = (payload.get('label') or '').strip()
    if not label:
        errors['label'] = 'Give it a name'
    elif len(label) > MAX_LABEL:
        errors['label'] = 'Name is too long'

    reg = register((payload.get('register') or '').strip())
    if reg is None:
        errors['register'] = 'Pick a register'
    elif not reg.schedulable:
        # Vehicle service is mileage-driven and preventive maintenance is
        # called when a machine stops; neither has a calendar due date.
        errors['register'] = f'{reg.label} cannot be put on a schedule'

    frequency = (payload.get('frequency') or '').strip()
    if frequency not in FREQUENCIES:
        errors['frequency'] = 'Pick how often'

    interval = _parse_int(payload.get('interval', 1))
    if interval is None or interval < 1:
        errors['interval'] = 'Must be 1 or more'
    elif interval > MAX_INTERVAL:
        errors['interval'] = f'Must be {MAX_INTERVAL} or less'

    weekday = None
    day_of_month = None
    if frequency == 'weekly':
        if payload.get('weekday') not in (None, ''):
            weekday = _parse_int(payload.get('weekday'))
            if weekday is None or not 0 <= weekday <= 6:
                errors['weekday'] = 'Pick a day of the week'
    elif frequency in MONTHLY_FREQUENCIES:
        if payload.get('day_of_month') not in (None, ''):
            day_of_month = _parse_int(payload.get('day_of_month'))
            if day_of_month is None or not 1 <= day_of_month <= 31:
                errors['day_of_month'] = 'Must be between 1 and 31'

    starts_on = _parse_date(payload.get('starts_on'))
    if starts_on is None:
        errors['starts_on'] = 'Pick a start date'

    ends_on = None
    if payload.get('ends_on'):
        ends_on = _parse_date(payload.get('ends_on'))
        if ends_on is None:
            errors['ends_on'] = 'Not a date'
        elif starts_on is not None and ends_on < starts_on:
            errors['ends_on'] = 'Cannot end before it starts'

    owner_id = None
    if payload.get('owner_id') not in (None, ''):
        owner_id = _parse_int(payload.get('owner_id'))
        if owner_id is None:
            errors['owner_id'] = 'Not a person'

    # --- assets ---------------------------------------------------------
    raw_assets = payload.get('asset_ids') or []
    if not isinstance(raw_assets, (list, tuple)):
        raw_assets = [raw_assets]
    asset_ids, available = [], set(available_asset_ids)
    for raw in raw_assets:
        value = _parse_int(raw)
        if value is None or value not in available:
            errors['asset_ids'] = 'One of those is no longer available'
            break
        if value not in asset_ids:
            asset_ids.append(value)

    if check_assets and reg is not None and 'register' not in errors:
        field = asset_field(reg)
        if field is None and asset_ids:
            errors['asset_ids'] = f'{reg.label} does not record an asset'
        elif field is not None and field.required and not asset_ids:
            # Otherwise "Log it" would open a form it cannot satisfy.
            errors['asset_ids'] = f'Pick at least one — {reg.label} needs a {field.label.lower()}'

    if errors:
        raise ValidationError(errors)

    return {
        'label': label,
        'register': reg.key,
        'frequency': frequency,
        'interval': interval,
        'weekday': weekday,
        'day_of_month': day_of_month,
        'starts_on': starts_on,
        'ends_on': ends_on,
        'owner_id': owner_id,
    }, asset_ids


def plan_from(values):
    """The duck-typed stand-in the generator needs, built from cleaned
    values — so a form can be previewed before it is ever saved."""
    return Plan(
        frequency=values['frequency'],
        interval=values['interval'],
        weekday=values['weekday'],
        day_of_month=values['day_of_month'],
        starts_on=values['starts_on'],
        ends_on=values['ends_on'],
    )


def preview_dates(values, count=PREVIEW_COUNT, today=None):
    """The next few dates this form would produce.

    The cheapest guard there is against "every 2 weeks" being typed where
    "every 2 months" was meant: he sees it before saving, rather than a
    month later as a run of missed inspections.
    """
    today = today or date.today()
    plan = plan_from(values)
    horizon = max(today, values['starts_on']) + timedelta(days=PREVIEW_HORIZON_DAYS)
    return occurrence_dates(plan, today, horizon)[:count]


def apply_payload(schedule, payload, assets_by_id):
    """Validate, then write onto the schedule. All-or-nothing: a rejected
    form leaves the existing schedule exactly as it was."""
    values, asset_ids = clean_payload(payload, tuple(assets_by_id))
    for name, value in values.items():
        setattr(schedule, name, value)
    schedule.assets = [assets_by_id[i] for i in asset_ids]
    return schedule


def serialize_schedule(schedule, today=None, entries=(), last_done=None):
    """One row of the schedule table.

    `entries` are the entries already filed against schedules, so the due
    column can tell "waiting on Monday" from "next Monday". `last_done`
    maps schedule id to the most recent date filed against it.
    """
    reg = register(schedule.register)
    return {
        'id': schedule.id,
        'label': schedule.label,
        'register': schedule.register,
        'register_label': reg.label if reg else schedule.register,
        'frequency': schedule.frequency,
        'interval': schedule.interval,
        'weekday': schedule.weekday,
        'day_of_month': schedule.day_of_month,
        'cadence': cadence_text(schedule),
        'cadence_short': cadence_short(schedule),
        'applies_to': applies_to_text(schedule),
        'due': due_status(schedule, entries, today),
        'last_done': (last_done or {}).get(schedule.id),
        'starts_on': schedule.starts_on,
        'ends_on': schedule.ends_on,
        'owner_id': schedule.owner_id,
        'owner': schedule.owner.name if schedule.owner else None,
        'assets': [{'id': a.id, 'label': a.label} for a in (schedule.assets or [])],
        'asset_ids': [a.id for a in (schedule.assets or [])],
        'active': schedule.active,
    }


DATE_FORMAT = '%d %b %Y'


def display_row(row):
    """The same row with every date already formatted, so the JSON a save
    returns carries no dates for the browser to reformat differently from
    the server."""
    due = row['due']
    out = dict(row)
    out['due'] = {
        'date_label': due['date'].strftime(DATE_FORMAT) if due['date'] else None,
        'label': due['label'],
        'overdue_days': due['overdue_days'],
    }
    out['last_done_label'] = (row['last_done'].strftime(DATE_FORMAT)
                              if row['last_done'] else None)
    out.pop('last_done', None)
    out.pop('starts_on', None)
    out.pop('ends_on', None)
    return out


def form_payload(row):
    """Just what the edit form needs, as JSON-safe values. Dates go out as
    ISO strings because that is what a date input reads; the table keeps the
    real date objects for formatting."""
    return {
        'id': row['id'],
        'label': row['label'],
        'register': row['register'],
        'frequency': row['frequency'],
        'interval': row['interval'],
        'weekday': row['weekday'],
        'day_of_month': row['day_of_month'],
        'starts_on': row['starts_on'].isoformat() if row['starts_on'] else '',
        'ends_on': row['ends_on'].isoformat() if row['ends_on'] else '',
        'owner_id': row['owner_id'],
        'asset_ids': row['asset_ids'],
    }


def form_options():
    """What the form may offer: the registers that can carry a schedule,
    and whether each one records an asset."""
    registers = []
    for reg in schedulable_registers():
        field = asset_field(reg)
        registers.append({
            'key': reg.key,
            'label': reg.label,
            'asset_label': field.label if field else None,
            'asset_required': bool(field and field.required),
        })
    return {
        'registers': registers,
        'frequencies': [{'value': v, 'label': l} for v, l in FREQUENCY_LABELS],
        'weekdays': [{'value': v, 'label': l} for v, l in WEEKDAYS],
        'monthly_frequencies': list(MONTHLY_FREQUENCIES),
    }
