"""
Turns a register declaration into table columns and cell view models, so
cell text and pill colours are testable without rendering HTML.
"""

from app.modules.hse.lib.computed import (
    days_open, days_to_expiry, effective_status,
)
from app.modules.hse.lib.overview import entry_title
from app.modules.hse.lib.registers import shows_asset_serial, table_fields
from app.modules.hse.lib.spend import amount_text
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
    'subject_id': ('subject', 'name'),
    'waiting_on_id': ('waiting_on', 'name'),
    'compliance_item_id': ('compliance_item', 'label'),
}


def _trailing_label(reg):
    """Header of the trailing computed column, or None for a log."""
    if reg.status_source == 'expiry':
        return 'Days to expiry'
    if reg.status_source == 'stored':
        return 'Days open'
    return None


def columns(reg):
    """Header labels: Ref, each in_table field, then computed columns. An
    expiry register has no status field, so it gets an extra Status column."""
    heads = ['Ref'] + [f.label for f in table_fields(reg)]
    if reg.status_source == 'expiry':
        heads.append('Status')
    trailing = _trailing_label(reg)
    if trailing:
        heads.append(trailing)
    return heads


def _cell(kind, text, modifier=None, tone=None):
    return {'kind': kind, 'text': text, 'modifier': modifier, 'tone': tone}


def _raw(entry, field):
    """The stored value behind a field: the related record's name, the
    column value, or the JSONB value."""
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
    if field.type == 'money':
        return _cell('mono', amount_text(value))
    if field.type == 'number':
        return _cell('mono', value)
    if field.type == 'textarea':
        # One line in the table; the full text is in the hover card.
        return _cell('clip', value)
    return _cell('text', value)


def row(entry, reg, today=None):
    """Every cell for one entry, in the same order as columns()."""
    cells = [_cell('mono', entry.ref)]
    cells += [cell(entry, f, reg, today) for f in table_fields(reg)]
    if reg.status_source == 'expiry':
        label = effective_status(entry, reg, today)
        cells.append(_cell('pill', label, status_modifier(label)) if label
                     else _cell('empty', '—'))
    if _trailing_label(reg):
        cells.append(_trailing(entry, reg, today))
    return cells


def _trailing(entry, reg, today=None):
    """Days open or days to expiry. Expired, and open over 30 days, get a
    warning tone."""
    if reg.status_source == 'expiry':
        remaining = days_to_expiry(entry, today)
        if remaining is None:
            return _cell('empty', '—')
        if remaining < 0:
            return _cell('text', f'{abs(remaining)} days ago', tone='expired')
        return _cell('text', f'{remaining} days')

    open_for = days_open(entry, today)
    if open_for is None:
        return _cell('empty', '—')
    if entry.closed_at is not None:
        return _cell('muted', f'{open_for} days')
    return _cell('text', f'{open_for} days', tone='overdue' if open_for > 30 else None)


def status_chips(reg, counts, total, today=None):
    """Filter chips: All, then every status the register can show, with
    counts (zero-count chips still render so the row stays stable). A log
    gets no chips."""
    if reg.status_source == 'none':
        return []
    if reg.status_source == 'expiry':
        labels = ('Valid', 'Expiring soon', 'Expired')
    else:
        labels = reg.statuses
    chips = [{'label': 'All', 'value': None, 'count': total}]
    chips += [{'label': s, 'value': s, 'count': counts.get(s, 0)} for s in labels]
    return chips


def peek(entry, reg, today=None):
    """Hover-card lines: the machine's serial on a machine register, the
    in_table=False fields, then the full text of clipped textarea fields.
    Empty values are skipped."""
    out = []
    asset = getattr(entry, 'asset', None)
    if shows_asset_serial(reg) and getattr(asset, 'serial_no', None):
        out.append({'label': 'Serial no.', 'text': asset.serial_no})
    hidden = [f for f in reg.fields if not f.in_table]
    long_text = [f for f in reg.fields if f.in_table and f.type == 'textarea']
    for field in hidden + long_text:
        c = cell(entry, field, reg, today)
        if c['kind'] != 'empty':
            out.append({'label': field.label, 'text': str(c['text'])})
    return out


def table_rows(entries, reg, today=None):
    """View rows: cells, hover card, and lowercased text for client-side
    search. On phones `title` heads the card, and `aside` (first field is a
    date) puts that date top right beside the ref."""
    fields = table_fields(reg)
    lead_is_date = bool(fields) and fields[0].type == 'date'
    out = []
    for entry in entries:
        cells = row(entry, reg, today)
        searchable = ' '.join(
            str(c['text']) for c in cells if c['kind'] != 'empty' and c['text'] is not None
        ).lower()
        out.append({'id': entry.id, 'ref': entry.ref, 'cells': cells,
                    'peek': peek(entry, reg, today), 'search': searchable,
                    'title': entry_title(entry), 'aside': lead_is_date})
    return out
