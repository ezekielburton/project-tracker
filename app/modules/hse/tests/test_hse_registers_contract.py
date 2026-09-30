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


def test_the_optional_behaviours_point_at_real_fields():
    """done_requires, interval_field, group_by, repeat_fields and unique_by
    each name a field of their own register."""
    for reg in HSE_REGISTERS:
        names = {fl.name for fl in reg.fields}
        named = list(reg.done_requires) + list(reg.repeat_fields) + [
            n for n in (reg.interval_field, reg.group_by, reg.unique_by) if n]
        missing = [n for n in named if n not in names]
        assert not missing, f'{reg.key}: no such field(s): {missing}'


def test_a_done_status_is_one_of_the_statuses_and_its_fields_are_optional_otherwise():
    for reg in HSE_REGISTERS:
        if reg.done_status:
            assert reg.done_status in reg.statuses, reg.key
        assert not reg.done_requires or reg.done_status, (
            f'{reg.key}: done_requires needs a done_status')
        fields = {fl.name: fl for fl in reg.fields}
        forced = [n for n in reg.done_requires if fields[n].required]
        assert not forced, f'{reg.key}: {forced} are always required already'


def test_an_interval_comes_from_a_dated_choice_on_an_asset():
    for reg in HSE_REGISTERS:
        if not reg.interval_field:
            continue
        field = next(fl for fl in reg.fields if fl.name == reg.interval_field)
        assert field.type == 'choice' and field.column is None, reg.key
        assert any(fl.type == 'asset' for fl in reg.fields), reg.key
        assert any(fl.column == 'entry_date' for fl in reg.fields), reg.key


def test_grouping_is_only_on_expiry_registers():
    """page_of pages whole groups from every loaded row, which only the
    expiry branch loads."""
    bad = [reg.key for reg in HSE_REGISTERS if reg.group_by and reg.status_source != 'expiry']
    assert not bad, 'group_by on a register that pages in SQL: ' + ', '.join(bad)


def test_a_ledger_is_a_log_with_one_line_per_item():
    for reg in HSE_REGISTERS:
        if reg.ledger:
            assert reg.status_source == 'none', reg.key
            assert reg.unique_by, f'{reg.key}: a ledger needs one line per item'
            assert 'moves' not in {fl.name for fl in reg.fields}, (
                f'{reg.key}: moves are kept by the ledger, not a form field')
        if reg.unique_by:
            field = next(fl for fl in reg.fields if fl.name == reg.unique_by)
            assert field.type == 'text' and field.column is None, reg.key


def test_every_register_has_reported_by_and_reported_to():
    from app.modules.hse.lib.registers import HSE_REGISTERS
    for reg in HSE_REGISTERS:
        cols = {f.name: (f.label, f.column) for f in reg.fields}
        assert cols.get('reported_by') == ('Reported by', 'reported_by_id'), reg.key
        assert cols.get('assigned_to') == ('Reported to', 'assigned_to_id'), reg.key
