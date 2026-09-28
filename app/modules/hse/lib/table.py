"""
Turns a register declaration into table columns and cell view models, so
cell text and pill colours are testable without rendering HTML.
"""

from datetime import date

from app.modules.hse.lib import flags, stock
from app.modules.hse.lib.computed import (
    days_open, days_to_expiry, effective_status, expiry_status,
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
    """Header of the trailing computed column, or None for a log. A
    register with a done_status logs things that happen, so nothing in it
    is ever open."""
    if reg.status_source == 'expiry':
        return 'Days to expiry'
    if reg.status_source == 'stored' and not reg.done_status:
        return 'Days open'
    return None


def _shown_fields(reg):
    """Table fields less the group_by field, which heads each group instead."""
    return tuple(f for f in table_fields(reg) if f.name != reg.group_by)


def _layout(reg):
    """Column plan shared by columns() and row(): ('field', f) per shown
    field, with Next due after the interval field and Next service after the
    mileage field, then the computed ones."""
    plan = []
    for field in _shown_fields(reg):
        plan.append(('field', field))
        if field.name == reg.interval_field:
            plan.append(('next_due', 'Next due'))
        if reg.km_due and field.name == reg.km_due[0]:
            plan.append(('next_service', 'Next service'))
    if reg.ledger:
        plan.append(('balance', 'Balance'))
    if reg.status_source == 'expiry':
        plan.append(('status', 'Status'))
    trailing = _trailing_label(reg)
    if trailing:
        plan.append(('trailing', trailing))
    return plan


def columns(reg):
    """Header labels: Ref, each in_table field, then computed columns. An
    expiry register has no status field, so it gets an extra Status column."""
    return ['Ref'] + [spec.label if kind == 'field' else spec
                      for kind, spec in _layout(reg)]


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


# Flag state -> cell tone: overdue reads red, due soon bold.
_FLAG_TONES = {'overdue': 'expired', 'soon': 'overdue'}


def _next_due_cell(entry, reg, current, today=None):
    """Next due for the latest entry per asset (`current` ids)."""
    if current is None or entry.id not in current:
        return _cell('empty', '—')
    state, due = flags.pm_state(entry, today or date.today(), reg)
    if due is None:
        return _cell('empty', '—')
    return _cell('text', due.strftime(DATE_FORMAT), tone=_FLAG_TONES.get(state))


def _next_service_cell(entry, current, readings):
    """Next service reading for the latest completed service per vehicle
    (`current` ids), against the vehicle's odometer in `readings`."""
    due_km = flags.next_service_km(entry) if current and entry.id in current else None
    if due_km is None:
        return _cell('empty', '—')
    state, _ = flags.service_state(entry, (readings or {}).get(entry.asset_id))
    return _cell('mono', flags.km_text(due_km), tone=_FLAG_TONES.get(state))


def _balance_cell(entry):
    """Balance with its unit; at or below the reorder level reads low."""
    return _cell('mono', stock.balance_text(entry),
                 tone='low' if stock.is_low_stock(entry) else None)


def row(entry, reg, today=None, current=None, readings=None):
    """Every cell for one entry, in the same order as columns(). `current`:
    ids of the latest entry per asset, for Next due and Next service;
    `readings`: odometer per vehicle, for Next service."""
    cells = [_cell('mono', entry.ref)]
    for kind, spec in _layout(reg):
        if kind == 'field':
            cells.append(cell(entry, spec, reg, today))
        elif kind == 'next_due':
            cells.append(_next_due_cell(entry, reg, current, today))
        elif kind == 'next_service':
            cells.append(_next_service_cell(entry, current, readings))
        elif kind == 'balance':
            cells.append(_balance_cell(entry))
        elif kind == 'status':
            label = effective_status(entry, reg, today)
            cells.append(_cell('pill', label, status_modifier(label)) if label
                         else _cell('empty', '—'))
        else:
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


def table_rows(entries, reg, today=None, current=None, readings=None):
    """View rows: cells, hover card, and lowercased text for client-side
    search. On phones `title` heads the card, and `aside` (first field is a
    date) puts that date top right beside the ref."""
    fields = _shown_fields(reg)
    lead_is_date = bool(fields) and fields[0].type == 'date'
    out = []
    for entry in entries:
        cells = row(entry, reg, today, current, readings)
        searchable = ' '.join(
            str(c['text']) for c in cells if c['kind'] != 'empty' and c['text'] is not None
        ).lower()
        out.append({'id': entry.id, 'ref': entry.ref, 'cells': cells,
                    'peek': peek(entry, reg, today), 'search': searchable,
                    'title': entry_title(entry), 'aside': lead_is_date})
    return out


def table_groups(groups, reg, today=None):
    """Grouped view rows. Each group heads with its name, item count and
    soonest due date (with that date's expiry status)."""
    field = next(f for f in reg.fields if f.name == reg.group_by)
    out = []
    for entries in groups:
        name = _raw(entries[0], field)
        dated = [e for e in entries if e.due_at is not None]
        soonest = min(dated, key=lambda e: e.due_at) if dated else None
        status = expiry_status(soonest, today) if soonest else None
        out.append({
            'label': name or f'No {field.label.lower()}',
            'count': len(entries),
            'soonest': soonest.due_at.strftime(DATE_FORMAT) if soonest else None,
            'status': status,
            'modifier': status_modifier(status) if status else None,
            'rows': table_rows(entries, reg, today),
        })
    return out
