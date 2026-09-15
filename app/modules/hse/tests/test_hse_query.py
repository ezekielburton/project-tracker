"""
The register list query: the chip counts, the total above them, and paging —
including the compliance branch that has to page in Python because its status
is computed from a date rather than stored.

DB-backed: page_of runs real queries, so these use db_session. Every row is
rolled back at teardown.
"""
from datetime import date, timedelta

from app.modules.hse.lib.query import empty_filters, page_of, PAGE_SIZE
from app.modules.hse.models import HseEntry, HseReference


TODAY = date(2026, 9, 14)


def _com(db_session, ref, due_at, compliance_item_id=None):
    """A compliance entry — status is computed from due_at."""
    row = HseEntry(register='compliance_renewal', ref=ref,
                   entry_date=date(2026, 1, 1), due_at=due_at,
                   compliance_item_id=compliance_item_id)
    db_session.add(row)
    return row


def _cert(db_session, label):
    """A compliance-item reference row. The certificate name lives here now,
    not in the entry's data blob, so search has to reach it through the join."""
    ref = HseReference(kind='compliance_item', label=label, active=True)
    db_session.add(ref)
    db_session.flush()
    return ref


def _inc(db_session, ref, status):
    """An incident — status is stored."""
    row = HseEntry(register='incidents', ref=ref,
                   entry_date=date(2026, 1, 1), status=status)
    db_session.add(row)
    return row


def test_the_all_count_on_an_expiry_register_matches_its_chips(db_session):
    """The fix: the computed-status branch counts 'All' from the chips, like
    every other register, so a certificate with no expiry date can't inflate
    the total above the chips beside it."""
    _com(db_session, 'COM-0001', TODAY + timedelta(days=100))  # Valid
    _com(db_session, 'COM-0002', TODAY + timedelta(days=10))   # Expiring soon
    _com(db_session, 'COM-0003', TODAY - timedelta(days=10))   # Expired
    _com(db_session, 'COM-0004', None)                         # no status, no chip
    db_session.flush()

    result = page_of('compliance_renewal', empty_filters(), today=TODAY)
    assert result['total_all'] == sum(result['counts'].values())
    assert result['total_all'] == 3


def test_the_all_count_on_a_stored_register_matches_its_chips(db_session):
    """The other branch, for parity — the two must define 'All' the same way."""
    for i in range(3):
        _inc(db_session, f'INC-100{i}', 'Open')
    for i in range(2):
        _inc(db_session, f'INC-200{i}', 'Closed')
    db_session.flush()

    result = page_of('incidents', empty_filters(), today=TODAY)
    assert result['total_all'] == sum(result['counts'].values()) == 5


def test_the_expiry_branch_pages_like_the_rest(db_session):
    for i in range(PAGE_SIZE + 3):
        _com(db_session, f'COM-{i:04d}', TODAY + timedelta(days=100))
    db_session.flush()

    first = page_of('compliance_renewal', empty_filters(), page=1, today=TODAY)
    assert len(first['rows']) == PAGE_SIZE
    assert first['total'] == PAGE_SIZE + 3
    assert first['pages'] == 2
    assert first['first'] == 1
    assert first['last'] == PAGE_SIZE

    second = page_of('compliance_renewal', empty_filters(), page=2, today=TODAY)
    assert len(second['rows']) == 3

    past_end = page_of('compliance_renewal', empty_filters(), page=3, today=TODAY)
    assert past_end['rows'] == []


def test_an_empty_register_reads_as_one_empty_page(db_session):
    result = page_of('compliance_renewal', empty_filters(), today=TODAY)
    assert result['total'] == 0
    assert result['pages'] == 1
    assert result['rows'] == []
    assert result['first'] == 0


def test_filtering_an_expiry_register_by_status_narrows_the_rows(db_session):
    _com(db_session, 'COM-0001', TODAY + timedelta(days=100))  # Valid
    _com(db_session, 'COM-0002', TODAY - timedelta(days=5))    # Expired
    db_session.flush()

    result = page_of('compliance_renewal',
                     {**empty_filters(), 'status': 'Expired'}, today=TODAY)
    assert result['total'] == 1
    assert result['total_all'] == 2            # 'All' still counts both
    assert result['rows'][0].ref == 'COM-0002'


def test_searching_compliance_by_certificate_name_finds_it(db_session):
    """The name moved off the data blob onto the reference row. Search has to
    reach it through the join, or searching a certificate by name comes back
    empty — the bug the promotion introduced."""
    iso = _cert(db_session, 'ISO 45001 Certification')
    fire = _cert(db_session, 'Fire safety certificate')
    _com(db_session, 'COM-0001', TODAY + timedelta(days=100), compliance_item_id=iso.id)
    _com(db_session, 'COM-0002', TODAY + timedelta(days=100), compliance_item_id=fire.id)
    db_session.flush()

    result = page_of('compliance_renewal',
                     {**empty_filters(), 'search': 'ISO 45001'}, today=TODAY)
    assert [r.ref for r in result['rows']] == ['COM-0001']
