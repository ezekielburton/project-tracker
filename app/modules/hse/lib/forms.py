"""
The entry form: view models, parsing and validation, all driven by the
register declaration. The ref is allocated on save and durations are
computed at read time, so neither is a form field.
"""

import re
from datetime import date, datetime

from sqlalchemy import func

from app.modules.hse.lib.metrics import parse_money
from app.modules.hse.lib.registers import register, shows_asset_serial
from app.modules.hse.lib.spend import stored_amount
from app.modules.hse.models import (
    EVENT_CLASSES, SEVERITIES, HseAsset, HseEntry, HsePerson, HseReference,
)


# "HSE" as a whole word in a person's name or role puts them first in pickers.
HSE_WORD = re.compile(r'\bhse\b', re.IGNORECASE)


def is_hse(person):
    return bool(HSE_WORD.search(f'{person.name} {person.role or ""}'))


def default_reporter(user):
    """The person a new entry's Reported by starts on: the one linked to
    `user`, else the only HSE person on the list. None when neither holds."""
    if user is None or getattr(user, 'id', None) is None:
        return None
    linked = HsePerson.query.filter_by(user_id=user.id, active=True).first()
    if linked:
        return linked.id
    hse = [p for p in HsePerson.query.filter_by(active=True).all() if is_hse(p)]
    return hse[0].id if len(hse) == 1 else None


# 'HH:MM', 24-hour: what <input type="time"> submits.
TIME_PATTERN = re.compile(r'([01]\d|2[0-3]):[0-5]\d')

# An amount: optional "AED", thousands commas in groups of three, up to 2
# decimals. No sign, so a negative is refused.
MONEY_PATTERN = re.compile(r'(?:AED\s*)?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?', re.IGNORECASE)
MONEY_ERROR = 'Enter an amount, e.g. 1,250.50'


class ValidationError(Exception):
    """Field name -> message. Raised before anything is written."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__('; '.join(f'{k}: {v}' for k, v in errors.items()))


def _options(field):
    """The active choices behind one field, as value/label dicts. May be
    empty; the form flags that case."""
    if field.type == 'choice':
        rows = (HseReference.query
                .filter_by(kind=field.choices_kind, active=True)
                .order_by(HseReference.sort_order, HseReference.label).all())
        # A column-backed choice is a foreign key, so its value is the id. A
        # JSONB choice stores the label: an id there has nothing to join to.
        if field.column is None:
            return [{'value': r.label, 'label': r.label} for r in rows]
        return [{'value': r.id, 'label': r.label} for r in rows]
    if field.type == 'person':
        rows = HsePerson.query.filter_by(active=True).order_by(HsePerson.name).all()
        # HSE people first, each group A–Z (the sort is stable).
        rows.sort(key=lambda r: not is_hse(r))
        return [{'value': r.id, 'label': f'{r.name} — {r.role}' if r.role else r.name,
                 'group': 'HSE' if is_hse(r) else 'Everyone else'}
                for r in rows]
    if field.type == 'asset':
        rows = HseAsset.query.filter_by(active=True).order_by(HseAsset.label).all()
        return [{'value': r.id, 'label': f'{r.label} ({r.ref})' if r.ref else r.label,
                 'serial': r.serial_no}
                for r in rows]
    if field.type == 'severity':
        return [{'value': s, 'label': s} for s in SEVERITIES]
    if field.type == 'event_class':
        return [{'value': c, 'label': c} for c in EVENT_CLASSES]
    return []


def _current(entry, field, prefill=None):
    """The entry's current value in input format, or the prefill value for
    a new entry."""
    if entry is None:
        return (prefill or {}).get(field.name)
    if field.column is None:
        return (entry.data or {}).get(field.name)
    value = getattr(entry, field.column, None)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _groups(options):
    """Options split by their 'group', in first-seen order, or [] when
    there is at most one group."""
    groups = []
    for opt in options:
        if 'group' not in opt:
            return []
        if not groups or groups[-1]['label'] != opt['group']:
            groups.append({'label': opt['group'], 'options': []})
        groups[-1]['options'].append(opt)
    return groups if len(groups) > 1 else []


def form_fields(reg, entry=None, prefill=None):
    """View models for the form, in declaration order. `prefill` (keyed by
    field name) applies to new entries only, e.g. the date and asset from
    the calendar's "Log it"."""
    if entry is None and reg.default_status:
        prefill = dict(prefill or {})
        for field in reg.fields:
            if field.type == 'status':
                prefill.setdefault(field.name, reg.default_status)
    closed_field = next((f.name for f in reg.fields if f.column == 'closed_at'), None)
    status_field = next((f for f in reg.fields if f.type == 'status'), None)
    status = _current(entry, status_field, prefill) if status_field else None
    out = []
    for field in reg.fields:
        options = _options(field)
        # Required only at the done status; the form toggles the star as the
        # status changes (hse_entry_modal.js).
        required_when = reg.done_status if field.name in reg.done_requires else None
        out.append({
            'name': field.name,
            'label': field.label,
            'type': field.type,
            'required': field.required,
            'required_when': required_when,
            'required_now': bool(required_when) and status == required_when,
            'options': options,
            # Person pickers split into HSE and everyone else when both exist.
            'groups': _groups(options),
            'value': _current(entry, field, prefill),
            'statuses': list(reg.statuses) if field.type == 'status' else [],
            # A choice field with nothing behind it cannot be filled in yet.
            'empty_list': field.type == 'choice' and not options,
            # For quick-add: which list to add to, and whether the field
            # stores the new row's id or its label (see _options).
            'choices_kind': field.choices_kind,
            'stores_label': field.column is None,
            # Machine registers show the picked asset's serial under the picker.
            'show_serial': field.type == 'asset' and shows_asset_serial(reg),
            # Picking this status fills the closed date (hse_entry_modal.js).
            'closed_status': reg.closed_status if field.type == 'status' else None,
            'closed_field': closed_field if field.type == 'status' else None,
        })
    return out


def _parse(field, raw, errors):
    """One submitted value, coerced. An unparseable value records an error
    in `errors` and returns None."""
    if raw in (None, '', []):
        if field.required:
            errors[field.name] = 'Required'
        return None

    if field.type == 'date':
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            errors[field.name] = 'Not a date'
            return None

    if field.type == 'time':
        if not isinstance(raw, str) or not TIME_PATTERN.fullmatch(raw):
            errors[field.name] = 'Not a time — use HH:MM (24-hour)'
            return None
        return raw

    if field.type in ('choice', 'person', 'asset'):
        # A JSONB choice keeps its label; column-backed fields are ids.
        if field.type == 'choice' and field.column is None:
            return raw
        try:
            return int(raw)
        except (TypeError, ValueError):
            errors[field.name] = 'Not a valid choice'
            return None

    if field.type == 'severity':
        if raw not in SEVERITIES:
            errors[field.name] = 'Not a severity'
            return None
        return raw

    if field.type == 'event_class':
        if raw not in EVENT_CLASSES:
            errors[field.name] = 'Not an event class'
            return None
        return raw

    if field.type == 'money':
        # A JSON number is accepted as its text; True would read as 1.
        valid = isinstance(raw, (str, int, float)) and not isinstance(raw, bool)
        text = str(raw).strip() if valid else ''
        if not MONEY_PATTERN.fullmatch(text):
            errors[field.name] = MONEY_ERROR
            return None
        return stored_amount(parse_money(text))

    if field.type == 'number':
        try:
            number = int(raw)
        except (TypeError, ValueError):
            errors[field.name] = 'Not a number'
            return None
        # Every number field is a count or a reading.
        if number < 0:
            errors[field.name] = 'Must be 0 or more'
            return None
        return number

    return raw


def apply_payload(entry, reg, payload):
    """Validate the whole submitted form, then write it onto `entry`.
    Raises ValidationError and writes nothing if any field fails."""
    errors = {}
    parsed = {}

    for field in reg.fields:
        parsed[field.name] = _parse(field, payload.get(field.name), errors)

    # A status outside this register's set would match no filter chip.
    status_field = next((f for f in reg.fields if f.type == 'status'), None)
    if status_field and parsed.get(status_field.name) not in (None, *reg.statuses):
        errors[status_field.name] = 'Not a status for this register'

    if status_field and reg.done_status and parsed.get(status_field.name) == reg.done_status:
        for name in reg.done_requires:
            if parsed.get(name) in (None, '') and name not in errors:
                errors[name] = f'Required when the status is {reg.done_status}'

    if reg.unique_by and reg.unique_by not in errors:
        taken = _taken_by(entry, reg, parsed.get(reg.unique_by))
        if taken is not None:
            errors[reg.unique_by] = f'Already on {taken.ref}' + (
                ' — record stock movements on that line instead' if reg.ledger else '')

    if errors:
        raise ValidationError(errors)

    # Closed with no date: it closed today. Any other status: it is not
    # closed, so the date goes and the entry counts as open again.
    closed = next((f for f in reg.fields if f.column == 'closed_at'), None)
    if status_field and reg.closed_status and closed:
        if parsed.get(status_field.name) != reg.closed_status:
            parsed[closed.name] = None
        elif parsed.get(closed.name) is None:
            parsed[closed.name] = date.today()

    data = dict(entry.data or {})
    for field in reg.fields:
        value = parsed[field.name]
        if field.column is None:
            data[field.name] = value
        else:
            setattr(entry, field.column, value)
    entry.data = data
    return entry


def _taken_by(entry, reg, value):
    """Another entry in the register whose unique_by text matches `value`
    (trimmed, any case), or None."""
    text = str(value or '').strip().lower()
    if not text:
        return None
    stored = func.lower(func.trim(HseEntry.data[reg.unique_by].astext))
    query = HseEntry.query.filter(HseEntry.register == reg.key, stored == text)
    if entry.id is not None:
        query = query.filter(HseEntry.id != entry.id)
    return query.order_by(HseEntry.id).first()


def blocking_empty_lists(reg):
    """Labels of required choice fields with no options yet. Saving is
    refused while any exist."""
    return [f.label for f in reg.fields
            if f.type == 'choice' and f.required and not _options(f)]
