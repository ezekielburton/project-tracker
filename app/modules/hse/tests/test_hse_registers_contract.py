"""
Contract test for HSE_REGISTERS: catches declaration mistakes that would otherwise
render a broken form silently. On failure, fix lib/registers.py to match the model.
"""
from pathlib import Path

from app.modules.hse.lib.registers import (
    BY_KEY, FIELD_TYPES, HSE_REGISTERS, RAIL_GROUPS, STATUS_SOURCES, jsonb_fields,
)
from app.modules.hse.models import HseEntry


ENTRY_FORM = Path(__file__).resolve().parents[1] / 'templates' / 'hse' / '_entry_modal.html'

# Registers that record when on the day something happened.
TIMED_REGISTERS = (
    'daily_log', 'incidents', 'first_aid', 'ppe_non_conformity', 'lost_time_injury',
    'general_inspection', 'vehicle_inspection', 'forklift_inspection',
    'induction_training', 'toolbox_talk',
)


def _entry_columns():
    return {c.key for c in HseEntry.__table__.columns}


def test_every_mapped_column_exists_on_the_model():
    columns = _entry_columns()
    bad = [
        f'{reg.key}.{fl.name} -> {fl.column}'
        for reg in HSE_REGISTERS for fl in reg.fields
        if fl.column is not None and fl.column not in columns
    ]
    assert not bad, (
        'These fields map to a column that does not exist on HseEntry: '
        + ', '.join(bad)
    )


def test_every_field_type_is_one_the_renderer_handles():
    bad = [
        f'{reg.key}.{fl.name} -> {fl.type}'
        for reg in HSE_REGISTERS for fl in reg.fields
        if fl.type not in FIELD_TYPES
    ]
    assert not bad, (
        'Unknown field types (add the type to FIELD_TYPES and teach the '
        'renderer, or fix the declaration): ' + ', '.join(bad)
    )


def test_choice_fields_name_a_reference_kind():
    bad = [
        f'{reg.key}.{fl.name}'
        for reg in HSE_REGISTERS for fl in reg.fields
        if fl.type == 'choice' and not fl.choices_kind
    ]
    assert not bad, 'Choice fields with no choices_kind: ' + ', '.join(bad)


def test_register_keys_and_ref_prefixes_are_unique():
    keys = [reg.key for reg in HSE_REGISTERS]
    prefixes = [reg.ref_prefix for reg in HSE_REGISTERS]
    assert len(keys) == len(set(keys)), 'Duplicate register key'
    assert len(prefixes) == len(set(prefixes)), 'Duplicate ref prefix'


def test_every_register_sits_in_a_real_rail_group():
    bad = [reg.key for reg in HSE_REGISTERS if reg.group not in RAIL_GROUPS]
    assert not bad, 'Registers in an unknown rail group: ' + ', '.join(bad)


def test_status_source_is_consistent_with_the_declared_statuses():
    for reg in HSE_REGISTERS:
        assert reg.status_source in STATUS_SOURCES, f'{reg.key}: unknown status_source'
        has_status_field = any(fl.column == 'status' for fl in reg.fields)

        if reg.status_source == 'stored':
            assert reg.statuses, f'{reg.key}: stored status needs a status list'
            assert has_status_field, (
                f'{reg.key}: stored status needs a field mapped to the status column')
        else:
            # Both 'expiry' and 'none' are read-only: nothing writes status.
            assert not reg.statuses, (
                f'{reg.key}: status is not stored, so it must not declare statuses')
            assert not has_status_field, (
                f'{reg.key}: status is not stored, so nothing may write the column')


def test_only_registers_that_can_be_logged_against_are_schedulable():
    """Every schedulable register has an entry_date field for occurrences to land on."""
    bad = [
        reg.key for reg in HSE_REGISTERS
        if reg.schedulable
        and not any(fl.column == 'entry_date' for fl in reg.fields)
    ]
    assert not bad, (
        'Schedulable registers with no entry date to land on: ' + ', '.join(bad))


def test_an_expiry_register_actually_captures_an_expiry_date():
    """Every expiry-status register has a due_at field."""
    bad = [
        reg.key for reg in HSE_REGISTERS
        if reg.status_source == 'expiry'
        and not any(fl.column == 'due_at' for fl in reg.fields)
    ]
    assert not bad, 'Expiry registers with no due_at field: ' + ', '.join(bad)


def test_jsonb_fields_are_the_ones_with_no_column():
    for reg in HSE_REGISTERS:
        for fl in jsonb_fields(reg):
            assert fl.column is None
        assert len(jsonb_fields(reg)) + len([f for f in reg.fields if f.column]) \
            == len(reg.fields)


def test_a_person_or_asset_field_is_always_a_foreign_key():
    """Person and asset fields map to an FK column, never JSONB."""
    bad = [
        f'{reg.key}.{fl.name}'
        for reg in HSE_REGISTERS for fl in reg.fields
        if fl.type in ('person', 'asset') and fl.column is None
    ]
    assert not bad, 'Person/asset fields not mapped to a column: ' + ', '.join(bad)


def test_the_entry_form_has_a_control_for_every_bespoke_field_type():
    """Types without their own branch fall back to a plain text box, which
    is only right for 'text'."""
    template = ENTRY_FORM.read_text()
    fallback = {'text'}
    missing = [t for t in FIELD_TYPES
               if t not in fallback and f"'{t}'" not in template]
    assert not missing, 'No form control for field types: ' + ', '.join(missing)


def test_the_timed_registers_ask_for_a_time_right_after_the_date():
    for key in TIMED_REGISTERS:
        names = [fl.name for fl in BY_KEY[key].fields]
        assert 'entry_time' in names, f'{key}: no time field'
        assert names.index('entry_time') == names.index('entry_date') + 1, (
            f'{key}: the time should sit right after the date')
        field = BY_KEY[key].fields[names.index('entry_time')]
        assert field.type == 'time'
        assert field.column is None, 'the time lives in data, not a column'
        assert not field.required
        assert not field.in_table, 'the time stays out of the table'


def test_default_and_closed_statuses_are_declared_statuses():
    for reg in HSE_REGISTERS:
        for name in ('default_status', 'closed_status'):
            value = getattr(reg, name)
            assert value is None or value in reg.statuses, (
                f'{reg.key}: {name} {value!r} is not one of its statuses')
        if reg.closed_status:
            assert any(fl.column == 'closed_at' for fl in reg.fields), (
                f'{reg.key}: closed_status needs a field mapped to closed_at')
