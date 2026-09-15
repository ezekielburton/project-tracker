"""Derived values: computed at read time, frozen once an entry closes,
and never counting someone else's delay against the officer.

These functions only read attributes, so the tests use a plain stub rather
than a mapped HseEntry — instantiating a mapped class configures every
mapper in the app, which would make date arithmetic depend on a database.
test_the_stub_only_uses_real_columns keeps the stub honest.
"""
from datetime import date

from app.modules.hse.lib.computed import (
    closed_on_time, days_open, days_owned, days_to_expiry, days_waiting,
    effective_status, expiry_status, severity_score,
)
from app.modules.hse.lib.registers import COMPLIANCE_RENEWAL, INCIDENTS
from app.modules.hse.models import HseEntry


TODAY = date(2026, 9, 14)

# Every attribute the computed functions read off an entry.
STUB_FIELDS = ('register', 'ref', 'entry_date', 'status', 'severity',
               'closed_at', 'due_at', 'waiting_since')


class _Entry:
    """Stands in for an HseEntry. Same attribute names, no ORM."""

    def __init__(self, **kw):
        for name in STUB_FIELDS:
            setattr(self, name, kw.pop(name, None))
        assert not kw, f'Unknown field(s): {sorted(kw)}'


def entry(**kw):
    kw.setdefault('register', 'incidents')
    kw.setdefault('ref', 'INC-0001')
    return _Entry(**kw)


def test_the_stub_only_uses_real_columns():
    """The stub is a stand-in, so a column rename must break it here rather
    than leave these tests passing against a field that no longer exists."""
    columns = {c.key for c in HseEntry.__table__.columns}
    missing = [name for name in STUB_FIELDS if name not in columns]
    assert not missing, (
        'The stub reads fields that are not columns on HseEntry: '
        + ', '.join(missing)
    )


def test_days_open_counts_to_today_while_open():
    e = entry(entry_date=date(2026, 9, 1))
    assert days_open(e, TODAY) == 13


def test_days_open_freezes_once_closed():
    e = entry(entry_date=date(2026, 9, 1), closed_at=date(2026, 9, 5))
    assert days_open(e, TODAY) == 4
    assert days_open(e, date(2027, 1, 1)) == 4


def test_days_to_expiry_goes_negative_once_passed():
    assert days_to_expiry(entry(due_at=date(2026, 9, 20)), TODAY) == 6
    assert days_to_expiry(entry(due_at=date(2026, 9, 1)), TODAY) == -13
    assert days_to_expiry(entry(), TODAY) is None


def test_expiry_status_matches_the_workbooks_thresholds():
    assert expiry_status(entry(due_at=date(2026, 12, 31)), TODAY) == 'Valid'
    assert expiry_status(entry(due_at=date(2026, 10, 1)), TODAY) == 'Expiring soon'
    assert expiry_status(entry(due_at=date(2026, 9, 14)), TODAY) == 'Expiring soon'
    assert expiry_status(entry(due_at=date(2026, 9, 13)), TODAY) == 'Expired'


def test_effective_status_is_stored_or_computed_per_register():
    stored = entry(status='Escalated')
    assert effective_status(stored, INCIDENTS, TODAY) == 'Escalated'

    renewal = entry(register='compliance_renewal', due_at=date(2026, 9, 1))
    assert effective_status(renewal, COMPLIANCE_RENEWAL, TODAY) == 'Expired'


def test_severity_score_matches_the_workbook():
    assert severity_score(entry(severity='High')) == 3
    assert severity_score(entry()) is None


def test_waiting_time_is_excluded_from_his_own_days():
    e = entry(entry_date=date(2026, 9, 1), waiting_since=date(2026, 9, 10))
    assert days_open(e, TODAY) == 13
    assert days_waiting(e, TODAY) == 4
    assert days_owned(e, TODAY) == 9


def test_an_entry_never_waited_on_owns_all_of_its_days():
    e = entry(entry_date=date(2026, 9, 1))
    assert days_waiting(e, TODAY) == 0
    assert days_owned(e, TODAY) == days_open(e, TODAY)


def test_the_sla_clock_pauses_while_parked_with_someone_else():
    """Twelve days open on a seven-day SLA, but six of them were spent
    waiting on someone else — that is on time."""
    e = entry(
        entry_date=date(2026, 9, 1), severity='High',
        waiting_since=date(2026, 9, 7), closed_at=date(2026, 9, 13),
    )
    assert days_open(e, TODAY) == 12
    assert closed_on_time(e, TODAY) is True


def test_closed_on_time_is_unknown_while_open_or_without_severity():
    assert closed_on_time(entry(entry_date=date(2026, 9, 1), severity='High'), TODAY) is None
    assert closed_on_time(entry(entry_date=date(2026, 9, 1),
                                closed_at=date(2026, 9, 2)), TODAY) is None
