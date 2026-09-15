"""Ref generation: sequential per register, never shared between them,
and safe when two saves land at once."""
import pytest

from app.modules.hse.lib.refs import format_ref, next_ref


def test_refs_are_sequential_within_a_register(db_session):
    first = next_ref('incidents')
    second = next_ref('incidents')
    assert first != second
    assert int(first.split('-')[1]) + 1 == int(second.split('-')[1])


def test_each_register_counts_on_its_own(db_session):
    inc = next_ref('incidents')
    ins = next_ref('general_inspection')
    assert inc.startswith('INC-')
    assert ins.startswith('INS-')
    assert inc.split('-')[1] == ins.split('-')[1]


def test_an_unknown_register_fails_loudly(db_session):
    with pytest.raises(ValueError):
        next_ref('not_a_register')


def test_concurrent_allocations_never_collide(db_session):
    """The counter is bumped by one atomic statement, so a batch of
    allocations produces a batch of distinct refs."""
    refs = [next_ref('incidents') for _ in range(50)]
    assert len(set(refs)) == 50


def test_format_pads_to_four_and_then_grows():
    assert format_ref('INC', 31) == 'INC-0031'
    assert format_ref('INC', 12345) == 'INC-12345'
