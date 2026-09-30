"""
Register table view model (lib/table.py): columns, cells, chips and hover peek, without rendering.
"""
from datetime import date

from app.modules.hse.lib.registers import (
    COMPLIANCE_RENEWAL, INCIDENTS, MACHINE_MAINTENANCE, VEHICLE_SERVICE, table_fields,
)
from app.modules.hse.lib.table import columns, peek, row, status_chips, table_rows


TODAY = date(2026, 9, 14)


class Stub:
    """Stands in for an HseEntry (see test_hse_computed.py for why)."""

    def __init__(self, **kw):
        self.id = kw.pop('id', 1)
        self.ref = kw.pop('ref', 'INC-0001')
        self.data = kw.pop('data', {})
        for name in ('entry_date', 'status', 'severity', 'closed_at', 'due_at',
                     'waiting_since', 'location', 'department', 'asset',
                     'reported_by', 'assigned_to', 'waiting_on', 'performed_by'):
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'


class Named:
    def __init__(self, **kw):
        self.label = kw.get('label')
        self.name = kw.get('name')


def test_columns_are_the_ref_then_the_declaration_then_one_computed():
    heads = columns(INCIDENTS)
    assert heads[0] == 'Ref'
    assert heads[-1] == 'Days open'
    assert len(heads) == len(table_fields(INCIDENTS)) + 2


def test_an_expiry_register_counts_down_instead_of_up():
    assert columns(COMPLIANCE_RENEWAL)[-1] == 'Days to expiry'


def test_a_related_record_renders_its_name_not_its_id():
    entry = Stub(entry_date=date(2026, 9, 1), status='Open', severity='High',
                 location=Named(label='Factory 1'),
                 assigned_to=Named(name='M. Dube'))
    texts = [c['text'] for c in row(entry, INCIDENTS, TODAY)]
    assert 'Factory 1' in texts
    assert 'M. Dube' in texts


def test_a_jsonb_field_renders_from_the_blob():
    entry = Stub(entry_date=date(2026, 9, 1), data={'incident_type': 'Slip/Fall'})
    assert 'Slip/Fall' in [c['text'] for c in row(entry, INCIDENTS, TODAY)]


def test_status_and_severity_become_pills():
    entry = Stub(entry_date=date(2026, 9, 1), status='Escalated', severity='Critical')
    pills = {c['text']: c['modifier'] for c in row(entry, INCIDENTS, TODAY) if c['kind'] == 'pill'}
    assert pills['Escalated'] == 'poppy'
    assert pills['Critical'] == 'poppy'


def test_an_expiry_registers_status_is_computed_not_read():
    """An expiry register's status pill is computed from due_at, in its own column."""
    entry = Stub(ref='COM-0001', entry_date=date(2025, 6, 1), due_at=date(2026, 6, 1))
    texts = [c['text'] for c in row(entry, COMPLIANCE_RENEWAL, TODAY)]
    assert 'Expired' in texts
    assert '105 days ago' in texts


def test_a_missing_value_renders_as_a_dash_not_none():
    entry = Stub(entry_date=date(2026, 9, 1))
    assert 'None' not in [str(c['text']) for c in row(entry, INCIDENTS, TODAY)]


def test_a_closed_entry_freezes_its_days_open():
    entry = Stub(entry_date=date(2026, 9, 1), closed_at=date(2026, 9, 5))
    assert row(entry, INCIDENTS, TODAY)[-1]['text'] == '4 days'


def test_chips_always_offer_every_status_even_at_zero():
    """Every status chip shows even at zero, so the chip row stays stable."""
    chips = status_chips(INCIDENTS, {'Open': 2}, 2, TODAY)
    assert [c['label'] for c in chips] == ['All', 'Open', 'In Progress', 'Escalated', 'Resolved']
    assert chips[0]['value'] is None and chips[0]['count'] == 2
    assert chips[2]['count'] == 0


def test_expiry_chips_are_the_computed_statuses():
    chips = status_chips(COMPLIANCE_RENEWAL, {}, 0, TODAY)
    assert [c['label'] for c in chips] == ['All', 'Valid', 'Expiring soon', 'Expired']


def test_search_text_covers_every_visible_cell():
    entry = Stub(entry_date=date(2026, 9, 1), severity='High',
                 location=Named(label='Warehouse B'), data={'incident_type': 'Electrical'})
    view = table_rows([entry], INCIDENTS, TODAY)[0]
    assert 'warehouse b' in view['search']
    assert 'electrical' in view['search']
    assert 'none' not in view['search']


def test_a_hidden_field_is_left_out_of_the_table_but_shown_on_hover():
    hidden = [f for f in INCIDENTS.fields if not f.in_table]
    assert hidden, 'Incidents should keep at least one field out of the table'
    assert not set(f.label for f in hidden) & set(columns(INCIDENTS))
    entry = Stub(entry_date=date(2026, 9, 1), severity='High',
                 department=Named(label='Logistics'),
                 data={'description': 'Pallet fell from racking'})
    card = {p['label']: p['text'] for p in peek(entry, INCIDENTS, TODAY)}
    assert card['Department'] == 'Logistics'
    assert card['What happened'] == 'Pallet fell from racking'   # full text
    assert 'Resolution date' not in card                         # empty values skipped


def test_an_expiry_register_shows_its_computed_status_and_reds_what_expired():
    heads = columns(COMPLIANCE_RENEWAL)
    assert heads[-2:] == ['Status', 'Days to expiry']
    expired = Stub(entry_date=date(2025, 1, 1), due_at=date(2026, 9, 1))
    cells = row(expired, COMPLIANCE_RENEWAL, TODAY)
    assert cells[-2]['kind'] == 'pill' and cells[-2]['text'] == 'Expired'
    assert cells[-1]['tone'] == 'expired'


def test_a_row_carries_the_phone_card_title_and_whether_it_leads_with_a_date():
    """Rows carry a phone-card title and `aside` (whether a leading date sits beside the ref)."""
    entry = Stub(entry_date=date(2026, 9, 1), location=Named(label='Warehouse B'),
                 data={'incident_type': 'Near miss'})
    view = table_rows([entry], INCIDENTS, TODAY)[0]
    assert view['title'] == 'Near miss — Warehouse B'
    assert view['aside'] is True
    # Compliance leads with the certificate, not a date.
    certificate = Stub(ref='COM-0001', data={'item': 'Trade licence'})
    assert table_rows([certificate], COMPLIANCE_RENEWAL, TODAY)[0]['aside'] is False


# --- money ----------------------------------------------------------------

def _cost_cell(value):
    cells = row(Stub(ref='SRV-0001', data={'cost': value}), VEHICLE_SERVICE, TODAY)
    index = columns(VEHICLE_SERVICE).index('Cost (AED)')
    return cells[index]


def test_money_cells_share_one_format_whatever_was_stored():
    """No unit (the column says AED); fils only when non-zero."""
    assert _cost_cell(3500)['text'] == '3,500'
    assert _cost_cell('1,850')['text'] == '1,850'
    assert _cost_cell('2400.5')['text'] == '2,400.50'
    assert _cost_cell('2400.00')['text'] == '2,400'
    assert _cost_cell(150)['kind'] == 'mono'


def test_a_legacy_value_that_is_not_an_amount_shows_as_stored():
    assert _cost_cell('TBC')['text'] == 'TBC'
    assert _cost_cell('')['kind'] == 'empty'


def test_the_hover_card_formats_money_too():
    """A money field kept out of the table still shows formatted."""
    hidden = MACHINE_MAINTENANCE._replace(fields=tuple(
        fl._replace(in_table=False) if fl.name == 'cost' else fl
        for fl in MACHINE_MAINTENANCE.fields))
    lines = peek(Stub(ref='MNT-0001', data={'cost': '12500.5'}), hidden, TODAY)
    assert {'label': 'Cost (AED)', 'text': '12,500.50'} in lines
