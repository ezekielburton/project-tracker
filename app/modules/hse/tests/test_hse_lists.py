"""
The officer's own lists.

The rule that matters most here is that nothing is deleted: entries already
filed point at these values, so a retired one is deactivated and stops being
offered. The second is quick-add's idempotence — typing a name that already
exists must never leave the dropdown showing it twice.
"""
from app.modules.hse.lib import lists
from app.modules.hse.models import REFERENCE_KINDS


def test_every_reference_kind_is_reachable_from_some_tab():
    """Declaring a register with a new choice list must not leave that list
    with nowhere to edit it."""
    reachable = set(lists.PROMINENT_KINDS) | set(lists.other_kinds())
    assert reachable == set(REFERENCE_KINDS)


def test_the_tab_strip_stays_short_as_registers_are_added():
    """Eighteen registers are still to come. Their choice lists share the
    'Other lists' tab rather than each earning one."""
    keys = [t['key'] for t in lists.tabs()]
    assert keys == ['location', 'department', 'people', 'assets', 'other']


def test_a_kind_with_no_friendly_name_still_reads_properly():
    assert lists.kind_label('location') == 'Locations'
    assert lists.kind_label('ppe_category') == 'Ppe category'


def test_severity_and_status_are_not_editable_lists():
    """Both are closed sets: severity drives the SLA clock and the
    performance page, statuses drive the chips and every open count. If one
    of these turns up here, something has made them user-editable."""
    editable = set(lists.PROMINENT_KINDS) | set(lists.other_kinds())
    assert 'severity' not in editable
    assert 'status' not in editable


def test_quick_add_reuses_an_existing_name(db_session):
    from app.modules.hse.models import HseReference
    db_session.add(HseReference(kind='location', label='Factory 1', active=True))
    db_session.flush()

    row, created = lists.find_or_revive_reference('location', 'Factory 1')
    assert row.id is not None, 'should have reused the existing row'
    assert created is False


def test_quick_add_revives_a_deactivated_name(db_session):
    """Re-adding something retired must bring it back, not create a second
    row the dropdown then shows twice."""
    from app.modules.hse.models import HseReference
    db_session.add(HseReference(kind='location', label='Old Yard', active=False))
    db_session.flush()

    row, created = lists.find_or_revive_reference('location', 'Old Yard')
    assert row.active is True
    assert created is True, 'a revival is a change worth reporting'
    assert HseReference.query.filter_by(kind='location', label='Old Yard').count() == 1


def test_a_genuinely_new_name_is_a_new_row(db_session):
    row, created = lists.find_or_revive_reference('location', 'Warehouse C')
    assert row.id is None, 'not added to the session yet — the caller does that'
    assert created is True
