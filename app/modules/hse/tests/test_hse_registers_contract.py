"""
Contract test for HSE_REGISTERS.

The declaration drives forms, tables, filters and the importer, and
nothing in Python checks it. A mistyped column name or an unhandled field
type would render a dead form with no traceback and no failing test —
these assertions are what turns that into a red build.

If one of these fails: fix the declaration in lib/registers.py, or, if
the model genuinely changed, update the declaration to match it.
"""
from app.modules.hse.lib.registers import (
    FIELD_TYPES, HSE_REGISTERS, RAIL_GROUPS, STATUS_SOURCES, jsonb_fields,
)
from app.modules.hse.models import HseEntry


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
    """A schedule generates occurrences someone must tick off, so its
    register has to be one he files entries into on a date. Vehicle service
    is mileage-driven and preventive maintenance is called when a machine
    stops — neither has a calendar due date, and neither may be scheduled."""
    bad = [
        reg.key for reg in HSE_REGISTERS
        if reg.schedulable
        and not any(fl.column == 'entry_date' for fl in reg.fields)
    ]
    assert not bad, (
        'Schedulable registers with no entry date to land on: ' + ', '.join(bad))


def test_an_expiry_register_actually_captures_an_expiry_date():
    """Its whole status comes from due_at, so a form that never sets it
    would render every row as having no status at all."""
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
    """An id inside JSONB has no referential integrity. Person and asset
    fields must map to a real FK column."""
    bad = [
        f'{reg.key}.{fl.name}'
        for reg in HSE_REGISTERS for fl in reg.fields
        if fl.type in ('person', 'asset') and fl.column is None
    ]
    assert not bad, 'Person/asset fields not mapped to a column: ' + ', '.join(bad)
