"""
Entry form validation: apply_payload is all-or-nothing. Most tests need no
database; the person picker and the Done-by data script do.
"""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

from app.modules.hse.lib.forms import ValidationError, apply_payload
from app.modules.hse.lib.metrics import parse_money
from app.modules.hse.lib.registers import (
    COMPLIANCE_RENEWAL, INCIDENTS, TRAINING_EXPENSES, Register, f,
)


class Stub:
    """Stands in for an HseEntry — see test_hse_computed.py for why."""

    def __init__(self):
        self.data = {}
        for name in ('entry_date', 'status', 'severity', 'closed_at', 'due_at',
                     'location_id', 'department_id', 'reported_by_id',
                     'assigned_to_id', 'asset_id', 'ref'):
            setattr(self, name, None)


VALID = {
    'entry_date': '2026-09-14',
    'location': '3',
    'department': '5',
    'event_class': 'Incident',
    'incident_type': 'Slip/Fall',
    'description': 'Wet floor by the loading bay.',
    'severity': 'High',
    'reported_by': '2',
    'assigned_to': '4',
    'status': 'Open',
    'closed_at': '',
}


def test_a_complete_form_lands_on_the_right_places():
    entry = apply_payload(Stub(), INCIDENTS, dict(VALID))
    assert entry.entry_date == date(2026, 9, 14)
    assert entry.location_id == 3          # promoted column, as an id
    assert entry.severity == 'High'
    assert entry.status == 'Open'
    assert entry.data['incident_type'] == 'Slip/Fall'   # JSONB
    assert 'location' not in entry.data                 # not duplicated


def test_every_missing_required_field_is_reported_at_once():
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), INCIDENTS, {})
    missing = e.value.errors
    for name in ('entry_date', 'location', 'event_class', 'incident_type',
                 'severity', 'reported_by', 'status'):
        assert missing[name] == 'Required', f'{name} should be required'


def test_nothing_is_written_when_validation_fails():
    """A rejected form leaves the entry untouched."""
    entry = Stub()
    payload = dict(VALID)
    payload['severity'] = ''
    with pytest.raises(ValidationError):
        apply_payload(entry, INCIDENTS, payload)
    assert entry.entry_date is None
    assert entry.location_id is None
    assert entry.data == {}


def test_an_unparseable_date_is_an_error_not_a_silent_none():
    payload = dict(VALID)
    payload['entry_date'] = '14/09/2026'
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), INCIDENTS, payload)
    assert e.value.errors['entry_date'] == 'Not a date'


def test_a_severity_outside_the_closed_set_is_refused():
    payload = dict(VALID)
    payload['severity'] = 'Catastrophic'
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), INCIDENTS, payload)
    assert e.value.errors['severity'] == 'Not a severity'


def test_an_event_class_outside_the_closed_set_is_refused():
    """event_class is a closed set (it drives the near-miss ratio); other values are refused."""
    payload = dict(VALID)
    payload['event_class'] = 'Almost'
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), INCIDENTS, payload)
    assert e.value.errors['event_class'] == 'Not an event class'


def test_a_status_from_another_register_is_refused():
    """A status not declared for this register (e.g. compliance's 'Valid') is refused."""
    payload = dict(VALID)
    payload['status'] = 'Valid'
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), INCIDENTS, payload)
    assert 'status' in e.value.errors


def test_an_optional_field_left_blank_is_simply_none():
    entry = apply_payload(Stub(), INCIDENTS, dict(VALID))
    assert entry.closed_at is None


def test_a_jsonb_choice_keeps_its_label_not_an_id():
    """JSONB choice fields store the label, since an id there has nothing to join to."""
    entry = apply_payload(Stub(), INCIDENTS, dict(VALID))
    assert entry.data['incident_type'] == 'Slip/Fall'


def test_an_expiry_register_needs_its_dates_and_writes_no_status():
    entry = apply_payload(Stub(), COMPLIANCE_RENEWAL, {
        'item': '7',
        'compliance_type': 'Certificate',
        'entry_date': '2025-06-01',
        'due_at': '2026-06-01',
        'assigned_to': '1',
    })
    assert entry.due_at == date(2026, 6, 1)
    assert entry.compliance_item_id == 7   # the certificate, by id
    assert 'item' not in entry.data
    assert entry.status is None, 'status is computed for this register'


# --- time of event ------------------------------------------------------------

def test_a_time_is_kept_as_hh_mm_in_the_blob():
    payload = dict(VALID, entry_time='07:05')
    entry = apply_payload(Stub(), INCIDENTS, payload)
    assert entry.data['entry_time'] == '07:05'


def test_the_time_is_optional():
    entry = apply_payload(Stub(), INCIDENTS, dict(VALID, entry_time=''))
    assert entry.data['entry_time'] is None


@pytest.mark.parametrize('raw', ['7:05', '24:00', '12:60', '07:05:00', '7pm',
                                 '07.05', ' 07:05', '0705', 7])
def test_anything_but_a_24_hour_hh_mm_is_refused(raw):
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), INCIDENTS, dict(VALID, entry_time=raw))
    assert e.value.errors['entry_time'] == 'Not a time — use HH:MM (24-hour)'


@pytest.mark.parametrize('raw', ['00:00', '09:30', '19:59', '23:59'])
def test_the_whole_day_is_accepted(raw):
    entry = apply_payload(Stub(), INCIDENTS, dict(VALID, entry_time=raw))
    assert entry.data['entry_time'] == raw


def test_a_required_time_left_blank_is_reported():
    reg = Register(key='t', label='T', group='incidents', ref_prefix='T',
                   status_source='none', statuses=(),
                   fields=(f('entry_time', 'Time', 'time', required=True),))
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), reg, {'entry_time': ''})
    assert e.value.errors['entry_time'] == 'Required'


# --- money ----------------------------------------------------------------

EXPENSE = {'entry_date': '2026-09-14', 'expense_category': 'Course fees'}


def _saved_amount(raw):
    return apply_payload(Stub(), TRAINING_EXPENSES, dict(EXPENSE, amount=raw)).data['amount']


@pytest.mark.parametrize('raw, stored', [
    ('1,250.50', '1250.50'), ('1250.5', '1250.50'), ('1250', '1250'),
    ('3500.00', '3500'), ('AED 300', '300'), (' aed 1,000 ', '1000'),
    ('0', '0'), (1200, '1200'), (12.5, '12.50'),
])
def test_an_amount_is_stored_as_a_plain_number(raw, stored):
    """Commas and the unit go; fils are kept only when non-zero."""
    assert _saved_amount(raw) == stored
    assert parse_money(stored) == parse_money(str(raw))


@pytest.mark.parametrize('raw', [
    '-50', 'abc', '12,50', '1,250.505', '1250.', '.5', '1e3', 'AED', True])
def test_a_negative_or_garbage_amount_is_refused(raw):
    entry = Stub()
    with pytest.raises(ValidationError) as caught:
        apply_payload(entry, TRAINING_EXPENSES, dict(EXPENSE, amount=raw))
    assert caught.value.errors == {'amount': 'Enter an amount, e.g. 1,250.50'}
    assert entry.data == {}, 'a refused save writes nothing'


def test_a_blank_optional_amount_is_allowed_and_a_required_one_is_not():
    optional = Register(key='x', label='X', group='fleet', ref_prefix='X',
                        status_source='none', statuses=(),
                        fields=(f('cost', 'Cost (AED)', 'money'),))
    assert apply_payload(Stub(), optional, {'cost': ''}).data['cost'] is None
    with pytest.raises(ValidationError) as caught:
        apply_payload(Stub(), TRAINING_EXPENSES, dict(EXPENSE, amount=''))
    assert caught.value.errors == {'amount': 'Required'}


def test_a_negative_count_is_refused():
    reg = Register(key='count_test', label='Count test', group='training',
                   ref_prefix='CT', status_source='none', statuses=(),
                   fields=(f('attendees', 'Attendees', 'number'),))
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), reg, {'attendees': '-3'})
    assert e.value.errors['attendees'] == 'Must be 0 or more'
    assert apply_payload(Stub(), reg, {'attendees': '0'}).data['attendees'] == 0


def test_hse_people_come_first_in_a_person_picker(db_session):
    from app.modules.hse.lib.forms import _groups, _options
    from app.modules.hse.models import HsePerson
    db_session.add_all([HsePerson(name='Aaron Admin', role='Clerk'),
                        HsePerson(name='Moses Danquah', role='HSE Officer')])
    db_session.flush()
    field = next(f for f in INCIDENTS.fields if f.name == 'reported_by')
    groups = _groups(_options(field))
    assert [g['label'] for g in groups] == ['HSE', 'Everyone else']
    assert groups[0]['options'][0]['label'].startswith('Moses Danquah')


DOER_MOVE = Path(__file__).resolve().parents[4] / 'migrations' / 'move_doers_to_done_by.py'


def test_doers_move_to_done_by_and_reported_by_is_filled_once(db_session):
    from app.modules.hse.models import HseEntry, HsePerson
    officer = HsePerson(name='Doer Officer', role='HSE Officer')
    nurse = HsePerson(name='Doer Nurse', role='Nurse')
    db_session.add_all([officer, nurse])
    db_session.flush()
    aid = HseEntry(register='first_aid', ref='DMV-1', entry_date=date(2026, 9, 14),
                   reported_by_id=nurse.id, data={})
    log = HseEntry(register='vehicle_mileage', ref='DMV-2', entry_date=date(2026, 9, 14), data={})
    db_session.add_all([aid, log])
    db_session.flush()

    spec = importlib.util.spec_from_file_location('move_doers_to_done_by', DOER_MOVE)
    move = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(move)
    conn = db_session.connection().connection
    first = move.run(conn)
    assert first['reporter'] == officer.id
    second = move.run(conn)
    assert (second['moved'], second['filled']) == (0, 0)

    db_session.expire_all()
    assert (aid.performed_by_id, aid.reported_by_id) == (nurse.id, officer.id)
    assert log.reported_by_id == officer.id
