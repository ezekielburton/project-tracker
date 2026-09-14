"""
What a register table says, without rendering one.

lib/table.py is where the declaration turns into columns and cells, so a
register gaining a field or changing its status source shows up here first.
"""
from datetime import date

from app.modules.hse.lib.registers import COMPLIANCE_RENEWAL, INCIDENTS
from app.modules.hse.lib.table import columns, row, status_chips, table_rows


TODAY = date(2026, 9, 14)


class Stub:
    """Stands in for an HseEntry — see test_hse_computed.py for why the
    real model is not instantiated here."""

    def __init__(self, **kw):
        self.id = kw.pop('id', 1)
        self.ref = kw.pop('ref', 'INC-0001')
        self.data = kw.pop('data', {})
        for name in ('entry_date', 'status', 'severity', 'closed_at', 'due_at',
                     'waiting_since', 'location', 'department', 'asset',
                     'reported_by', 'assigned_to', 'waiting_on'):
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
    assert len(heads) == len(INCIDENTS.fields) + 2


def test_an_expiry_register_counts_down_instead_of_up():
    assert columns(COMPLIANCE_RENEWAL)[-1] == 'Days to expiry'


def test_a_related_record_renders_its_name_not_its_id():
    entry = Stub(entry_date=date(2026, 9, 1), status='Open', severity='High',
                 location=Named(label='Factory 1'),
                 reported_by=Named(name='M. Dube'))
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
    """Nothing writes the status column for these, so the pill has to come
    from the expiry date."""
    entry = Stub(ref='COM-0001', entry_date=date(2025, 6, 1), due_at=date(2026, 6, 1))
    texts = [c['text'] for c in row(entry, COMPLIANCE_RENEWAL, TODAY)]
    assert 'Expired' not in texts  # no status field is declared on this register
    assert '105 days ago' in texts


def test_a_missing_value_renders_as_a_dash_not_none():
    entry = Stub(entry_date=date(2026, 9, 1))
    assert 'None' not in [str(c['text']) for c in row(entry, INCIDENTS, TODAY)]


def test_a_closed_entry_freezes_its_days_open():
    entry = Stub(entry_date=date(2026, 9, 1), closed_at=date(2026, 9, 5))
    assert row(entry, INCIDENTS, TODAY)[-1]['text'] == '4 days'


def test_chips_always_offer_every_status_even_at_zero():
    """The chip row must not reshuffle as rows are filed."""
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
