"""
The entry form — built from the same declaration the table is built from.

A register gaining a field gains a form row, a validation rule and a saved
value without anything here changing. What a field cannot do is invent a
value the module computes: the ref and every duration are rendered locked.
"""

from datetime import date, datetime

from app.modules.hse.lib.registers import register
from app.modules.hse.models import (
    SEVERITIES, HseAsset, HsePerson, HseReference,
)


# Rendered read-only, with the reason. The ref is allocated on save and the
# durations are computed at read time — neither is ever typed.
LOCKED_FIELDS = (
    {'name': 'ref', 'label': 'Reference', 'note': 'Generated on save'},
)


class ValidationError(Exception):
    """Field name -> message. Raised before anything is written."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__('; '.join(f'{k}: {v}' for k, v in errors.items()))


def _options(field):
    """The choices behind one field, newest lists first. An empty list is
    returned as-is — the form says so rather than showing a blank select."""
    if field.type == 'choice':
        rows = (HseReference.query
                .filter_by(kind=field.choices_kind, active=True)
                .order_by(HseReference.sort_order, HseReference.label).all())
        # A choice mapped to a column is a foreign key, so the id is the
        # value. One that falls into JSONB stores the label instead — an id
        # in the blob has nothing to join back to and would render as a
        # number in the table.
        if field.column is None:
            return [{'value': r.label, 'label': r.label} for r in rows]
        return [{'value': r.id, 'label': r.label} for r in rows]
    if field.type == 'person':
        rows = HsePerson.query.filter_by(active=True).order_by(HsePerson.name).all()
        return [{'value': r.id, 'label': f'{r.name} — {r.role}' if r.role else r.name}
                for r in rows]
    if field.type == 'asset':
        rows = HseAsset.query.filter_by(active=True).order_by(HseAsset.label).all()
        return [{'value': r.id, 'label': f'{r.label} ({r.ref})' if r.ref else r.label}
                for r in rows]
    if field.type == 'severity':
        return [{'value': s, 'label': s} for s in SEVERITIES]
    return []


def _current(entry, field, prefill=None):
    """The value already on an entry, in the shape the input wants — or, on
    a new entry opened from the calendar, the value the day and the
    occurrence already decided."""
    if entry is None:
        return (prefill or {}).get(field.name)
    if field.column is None:
        return (entry.data or {}).get(field.name)
    value = getattr(entry, field.column, None)
    if isinstance(value, date):
        return value.isoformat()
    return value


def form_fields(reg, entry=None, prefill=None):
    """View models for the form, in declaration order.

    `prefill` is keyed by field name and only applies to a new entry: the
    calendar's "Log it" already knows the date and the asset, and making
    him retype them is how the wrong vehicle ends up on the record.
    """
    out = []
    for field in reg.fields:
        options = _options(field)
        out.append({
            'name': field.name,
            'label': field.label,
            'type': field.type,
            'required': field.required,
            'options': options,
            'value': _current(entry, field, prefill),
            'statuses': list(reg.statuses) if field.type == 'status' else [],
            # A choice field with nothing behind it cannot be filled in yet.
            'empty_list': field.type == 'choice' and not options,
            # Quick-add needs both: which list to add to, and whether this
            # field stores the new row's id or its label (see _options).
            'choices_kind': field.choices_kind,
            'stores_label': field.column is None,
        })
    return out


def _parse(field, raw, errors):
    """One submitted value, coerced. Anything unparseable records an error
    rather than silently becoming None."""
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

    if field.type in ('choice', 'person', 'asset'):
        # Only a field backed by a foreign-key column is an id. A JSONB
        # choice keeps the label it was picked as.
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

    if field.type == 'number':
        try:
            return int(raw)
        except (TypeError, ValueError):
            errors[field.name] = 'Not a number'
            return None

    return raw


def apply_payload(entry, reg, payload):
    """Validate a whole submitted form, then write it onto `entry`.

    Whole-form, not field-by-field: an entry has required fields, and a
    per-field save would leave half-written records behind. Nothing is
    written unless every field passes.
    """
    errors = {}
    parsed = {}

    for field in reg.fields:
        parsed[field.name] = _parse(field, payload.get(field.name), errors)

    # A status this register does not recognise would sail past the chips.
    status_field = next((f for f in reg.fields if f.type == 'status'), None)
    if status_field and parsed.get(status_field.name) not in (None, *reg.statuses):
        errors[status_field.name] = 'Not a status for this register'

    if errors:
        raise ValidationError(errors)

    data = dict(entry.data or {})
    for field in reg.fields:
        value = parsed[field.name]
        if field.column is None:
            data[field.name] = value
        else:
            setattr(entry, field.column, value)
    entry.data = data
    return entry


def blocking_empty_lists(reg):
    """Required choice fields with no options yet. Saving is refused rather
    than filing an entry with a hole where a location should be."""
    return [f.label for f in reg.fields
            if f.type == 'choice' and f.required and not _options(f)]
