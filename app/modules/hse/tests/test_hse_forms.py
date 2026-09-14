"""
Validating a submitted entry.

apply_payload is all-or-nothing on purpose: an entry has required fields,
and a per-field save would leave half-written incidents behind. These cover
the rules without a database — the option lists are queried separately.
"""
from datetime import date

import pytest

from app.modules.hse.lib.forms import ValidationError, apply_payload
from app.modules.hse.lib.registers import COMPLIANCE_RENEWAL, INCIDENTS


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
    for name in ('entry_date', 'location', 'incident_type', 'severity',
                 'reported_by', 'status'):
        assert missing[name] == 'Required', f'{name} should be required'


def test_nothing_is_written_when_validation_fails():
    """All-or-nothing: a rejected form must not half-fill the entry."""
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


def test_a_status_from_another_register_is_refused():
    """'Valid' belongs to compliance. Accepting it here would file an entry
    no filter chip on this register could ever find."""
    payload = dict(VALID)
    payload['status'] = 'Valid'
    with pytest.raises(ValidationError) as e:
        apply_payload(Stub(), INCIDENTS, payload)
    assert 'status' in e.value.errors


def test_an_optional_field_left_blank_is_simply_none():
    entry = apply_payload(Stub(), INCIDENTS, dict(VALID))
    assert entry.closed_at is None


def test_a_jsonb_choice_keeps_its_label_not_an_id():
    """An id inside the blob has nothing to join back to, and the table
    would render it as a bare number."""
    entry = apply_payload(Stub(), INCIDENTS, dict(VALID))
    assert entry.data['incident_type'] == 'Slip/Fall'


def test_an_expiry_register_needs_its_dates_and_writes_no_status():
    entry = apply_payload(Stub(), COMPLIANCE_RENEWAL, {
        'item': 'ISO 45001 Certification',
        'compliance_type': 'Certificate',
        'entry_date': '2025-06-01',
        'due_at': '2026-06-01',
        'assigned_to': '1',
    })
    assert entry.due_at == date(2026, 6, 1)
    assert entry.data['item'] == 'ISO 45001 Certification'
    assert entry.status is None, 'status is computed for this register'
