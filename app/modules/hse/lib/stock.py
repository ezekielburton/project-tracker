"""
Stock lines (ledger registers): movements kept in data['moves'] and the
balance worked out from them at read time. The balance is never stored.
"""

from datetime import date

from app.modules.hse.lib.forms import ValidationError


# A count sets the balance to what was counted; the others add or take away.
MOVE_KINDS = ('received', 'issued', 'count')

KIND_LABELS = {'received': 'Received', 'issued': 'Issued', 'count': 'Count'}

NOTE_MAX = 200


def _number(value):
    """A stored quantity as an int, or None when it is not one."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def moves(entry):
    """The line's movements in date order; same-day moves keep the order
    they were recorded in."""
    data = entry.data or {}
    out = [m for m in data.get('moves') or () if isinstance(m, dict)]
    # Snapshot quantities on lines the merge script has not reached yet.
    for kind in ('received', 'issued'):
        qty = _number(data.get(kind))
        if qty and entry.entry_date is not None:
            out.append({'date': entry.entry_date.isoformat(), 'kind': kind, 'qty': qty})
    return sorted(out, key=lambda m: str(m.get('date') or ''))


def balance(entry):
    """Opening stock, then every movement in date order."""
    total = _number((entry.data or {}).get('opening_stock')) or 0
    for move in moves(entry):
        qty = _number(move.get('qty'))
        if qty is None:
            continue
        if move.get('kind') == 'received':
            total += qty
        elif move.get('kind') == 'issued':
            total -= qty
        elif move.get('kind') == 'count':
            total = qty
    return total


def is_low_stock(entry):
    """A reorder level is set and the balance is at or below it."""
    level = _number((entry.data or {}).get('reorder_level'))
    return level is not None and balance(entry) <= level


def balance_text(entry):
    """'42 Box': the balance with the line's unit, when it has one."""
    unit = (entry.data or {}).get('unit')
    return f'{balance(entry)} {unit}' if unit else str(balance(entry))


def history(entry, names=None):
    """Movements newest first, for the entry overlay. `names` maps user id
    to name."""
    names = names or {}
    out = []
    for move in reversed(moves(entry)):
        try:
            day = date.fromisoformat(str(move.get('date')))
        except ValueError:
            day = None
        out.append({
            'date': day,
            'kind': move.get('kind'),
            'label': KIND_LABELS.get(move.get('kind'), move.get('kind')),
            'qty': move.get('qty'),
            'note': move.get('note') or '',
            'by': names.get(move.get('by_id')),
        })
    return out


def mover_ids(entry):
    """User ids behind the line's movements, to look their names up."""
    return {m.get('by_id') for m in moves(entry) if m.get('by_id')}


def add_move(entry, payload, by_id, today=None):
    """Validate one movement and append it to the line. Raises
    ValidationError and writes nothing if any part fails."""
    today = today or date.today()
    payload = payload or {}
    errors = {}

    kind = payload.get('kind')
    if kind not in MOVE_KINDS:
        errors['kind'] = 'Pick received, issued or count'

    day = None
    try:
        day = date.fromisoformat(str(payload.get('date') or '').strip())
    except ValueError:
        errors['date'] = 'Not a date'
    if day is not None and day > today:
        errors['date'] = 'Cannot be later than today'

    raw = payload.get('qty')
    qty = None
    if not isinstance(raw, bool):
        try:
            qty = int(str(raw).strip())
        except (TypeError, ValueError):
            qty = None
    # A count of zero is real (the shelf is empty); a movement of zero is not.
    lowest = 0 if kind == 'count' else 1
    if qty is None or qty < lowest:
        errors['qty'] = ('Enter a whole number, 0 or more' if kind == 'count'
                         else 'Enter a whole number above 0')

    note = str(payload.get('note') or '').strip()
    if len(note) > NOTE_MAX:
        errors['note'] = f'Keep it under {NOTE_MAX} characters'

    if errors:
        raise ValidationError(errors)

    data = dict(entry.data or {})
    # A new list, so SQLAlchemy sees the JSONB change.
    data['moves'] = list(data.get('moves') or []) + [{
        'date': day.isoformat(), 'kind': kind, 'qty': qty,
        'note': note or None, 'by_id': by_id,
    }]
    entry.data = data
    return entry
