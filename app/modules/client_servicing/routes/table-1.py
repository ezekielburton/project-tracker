"""
Turns a register declaration into table columns and rendered cells.

The template only loops; what a cell says and which pill colour it takes is
decided here, so it can be tested without rendering HTML.
"""

from app.modules.hse.lib.computed import (
    days_open, days_to_expiry, effective_status,
)
from app.modules.hse.lib.vocab import severity_modifier, status_modifier


DATE_FORMAT = '%d %b %Y'

# Promoted columns that hold a related record rather than a value, and the
# attribute on it that reads as its name.
RELATION_ATTRS = {
    'location_id': ('location', 'label'),
    'department_id': ('department', 'label'),
    'asset_id': ('asset', 'label'),
    'reported_by_id': ('reported_by', 'name'),
    'assigned_to_id': ('assigned_to', 'name'),
    'waiting_on_id': ('waiting_on', 'name'),
}


def columns(reg):
    """Header labels, in declaration order: the ref, each declared field,
    then the one computed column that register earns."""
    heads = ['Ref'] + [f.label for f in reg.fields]
    heads.append('Days to expiry' if reg.status_source == 'expiry' else 'Days open')
    return heads


def _cell(kind, text, modifier=None, tone=None):
    return {'kind': kind, 'text': text, 'modifier': modifier, 'tone': tone}


def _raw(entry, field):
    """The stored value behind a field — a column when it maps to one, else
    whatever the JSONB blob holds."""
    if field.column is None:
        return (entry.data or {}).get(field.name)
    if field.column in RELATION_ATTRS:
        rel, attr = RELATION_ATTRS[field.column]
        related = getattr(entry, rel, None)
        return getattr(related, attr, None) if related else None
    return getattr(entry, field.column, None)


def cell(entry, field, reg, today=None):
    """One rendered cell."""
    if field.type == 'status':
        label = effective_status(entry, reg, today)
        return _cell('pill', label, status_modifier(label)) if label else _cell('empty', '—')

    if field.type == 'severity':
        label = _raw(entry, field)
        return _cell('pill', label, severity_modifier(label)) if label else _cell('empty', '—')

    value = _raw(entry, field)
    if value is None or value == '':
        return _cell('empty', '—')

    if field.type == 'date':
        return _cell('text', value.strftime(DATE_FORMAT))
    if field.type in ('number', 'money'):
        return _cell('mono', value)
    return _cell('text', value)


def row(entry, reg, today=None):
    """Every cell for one entry, ref first and the computed column last."""
    cells = [_cell('mono', entry.ref)]
    cells += [cell(entry, f, reg, today) for f in reg.fields]
    cells.append(_trailing(entry, reg, today))
    return cells


def _trailing(entry, reg, today=None):
    """Days open, or days to expiry — computed, never stored. Overdue and
    expired read as a warning rather than a plain number."""
    if reg.status_source == 'expiry':
        remaining = days_to_expiry(entry, today)
        if remaining is None:
            return _cell('empty', '—')
        if remaining < 0:
            return _cell('text', f'{abs(remaining)} days ago', tone='overdue')
        return _cell('text', f'{remaining} days')

    open_for = days_open(entry, today)
    if open_for is None:
        return _cell('empty', '—')
    if entry.closed_at is not None:
        return _cell('muted', f'{open_for} days')
    return _cell('text', f'{open_for} days', tone='overdue' if open_for > 30 else None)


def status_chips(reg, counts, total, today=None):
    """The filter row: All, then each status this register can show, with
    its count. A status with no rows behind it still renders, so the set of
    chips does not jump around as rows are filed."""
    if reg.status_source == 'expiry':
        labels = ('Valid', 'Expiring soon', 'Expired')
    else:
        labels = reg.statuses
    chips = [{'label': 'All', 'value': None, 'count': total}]
    chips += [{'label': s, 'value': s, 'count': counts.get(s, 0)} for s in labels]
    return chips


def table_rows(entries, reg, today=None):
    """View rows for the template: the cells, plus the flattened text the
    client-side search filters on."""
    out = []
    for entry in entries:
        cells = row(entry, reg, today)
        searchable = ' '.join(
            str(c['text']) for c in cells if c['kind'] != 'empty' and c['text'] is not None
        ).lower()
        out.append({'id': entry.id, 'cells': cells, 'search': searchable})
    return out
