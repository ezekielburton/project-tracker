"""
Stores registers: the PPE register grouped by employee (paged by whole
employees, with "Save & add another"), material request unit and cost, and
the Lost tool status.
"""
import re
from datetime import date, timedelta
from decimal import Decimal

from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib.metrics import spend_by_area, spend_of
from app.modules.hse.lib.query import OPEN_STATUSES, PAGE_SIZE, SpendRow, empty_filters, page_of
from app.modules.hse.lib.registers import MATERIAL_REQUEST, PPE_REGISTER, TOOLS_INVENTORY
from app.modules.hse.lib.table import columns, table_groups
from app.modules.hse.lib.vocab import status_modifier
from app.modules.hse.models import HseEntry, HsePerson, HseReference


TODAY = date(2026, 9, 14)


def _person(db_session, name):
    person = HsePerson(name=name)
    db_session.add(person)
    db_session.flush()
    return person


def _ppe(db_session, person, ref, due_in, issued=date(2026, 1, 1), kind='Gloves'):
    entry = HseEntry(register='ppe_register', ref=ref, entry_date=issued,
                     subject_id=person.id if person else None,
                     due_at=TODAY + timedelta(days=due_in), data={'ppe_type': kind})
    db_session.add(entry)
    return entry


# --- grouping -------------------------------------------------------------

def test_rows_group_under_each_employee_a_to_z(db_session):
    zed, amy = _person(db_session, 'Zed Stores'), _person(db_session, 'Amy Stores')
    _ppe(db_session, zed, 'PPG-1', 100)
    _ppe(db_session, amy, 'PPG-2', 50, issued=date(2026, 3, 1))
    _ppe(db_session, amy, 'PPG-3', -5, issued=date(2026, 2, 1))
    _ppe(db_session, None, 'PPG-4', 10)
    db_session.flush()

    page = page_of('ppe_register', dict(empty_filters(), search='PPG-'), today=TODAY)
    assert [[e.ref for e in g] for g in page['groups']] == [
        ['PPG-2', 'PPG-3'], ['PPG-1'], ['PPG-4']], 'A-Z, rows newest first, no employee last'
    assert [e.ref for e in page['rows']] == ['PPG-2', 'PPG-3', 'PPG-1', 'PPG-4']


def test_a_group_heads_with_its_count_and_soonest_replacement(db_session):
    amy = _person(db_session, 'Amy Heads')
    _ppe(db_session, amy, 'PPH-1', 200)
    _ppe(db_session, amy, 'PPH-2', 12)
    db_session.flush()
    page = page_of('ppe_register', dict(empty_filters(), search='PPH-'), today=TODAY)

    head = table_groups(page['groups'], PPE_REGISTER, TODAY)[0]
    assert (head['label'], head['count']) == ('Amy Heads', 2)
    assert head['soonest'] == (TODAY + timedelta(days=12)).strftime('%d %b %Y')
    assert (head['status'], head['modifier']) == ('Expiring soon', status_modifier('Expiring soon'))
    assert [r['ref'] for r in head['rows']] == ['PPH-2', 'PPH-1']


def test_the_employee_column_moves_into_the_group_head():
    assert 'Employee' not in columns(PPE_REGISTER)
    assert columns(PPE_REGISTER)[1] == 'PPE type'


def test_a_page_never_splits_an_employee(db_session):
    # Two people with PAGE_SIZE - 1 and 3 items: the second would straddle
    # the page boundary, so it moves whole onto page 1 (28 rows) ...
    first, second, third = (_person(db_session, n) for n in ('A Pager', 'B Pager', 'C Pager'))
    for i in range(PAGE_SIZE - 1):
        _ppe(db_session, first, f'PPP-A{i:02d}', 100)
    for i in range(3):
        _ppe(db_session, second, f'PPP-B{i}', 100)
    for i in range(2):
        _ppe(db_session, third, f'PPP-C{i}', 100)
    db_session.flush()
    filters = dict(empty_filters(), search='PPP-')

    one = page_of('ppe_register', filters, page=1, today=TODAY)
    assert [len(g) for g in one['groups']] == [PAGE_SIZE - 1, 3]
    assert (one['first'], one['last'], one['total'], one['pages']) == (1, PAGE_SIZE + 2, PAGE_SIZE + 4, 2)
    # ... and the next employee starts page 2.
    two = page_of('ppe_register', filters, page=2, today=TODAY)
    assert sorted(e.ref for e in two['rows']) == ['PPP-C0', 'PPP-C1']
    assert (two['first'], two['last']) == (PAGE_SIZE + 3, PAGE_SIZE + 4)
    assert page_of('ppe_register', filters, page=3, today=TODAY)['rows'] == []


def test_a_status_chip_still_filters_before_grouping(db_session):
    amy = _person(db_session, 'Amy Filter')
    _ppe(db_session, amy, 'PPF-1', 200)
    _ppe(db_session, amy, 'PPF-2', -3)
    db_session.flush()
    page = page_of('ppe_register', dict(empty_filters(), search='PPF-', status='Expired'),
                   today=TODAY)
    assert [[e.ref for e in g] for g in page['groups']] == [['PPF-2']]
    assert page['total_all'] == 2


def test_the_register_page_renders_its_groups(app, client, db_session):
    _officer(app, client, db_session)
    amy = _person(db_session, 'Amy Rendered')
    _ppe(db_session, amy, 'PPR-1', 40)
    db_session.flush()
    with app.test_request_context():
        url = url_for('hse.register_page', group_key='stores', register_key='ppe_register',
                      q='PPR-1')
    html = client.get(url).get_data(as_text=True)
    assert 'class="hse-group-row"' in html
    assert '<span class="hse-group-name">Amy Rendered</span>' in html


# --- save & add another ---------------------------------------------------

def _officer(app, client, db_session):
    user = User(name='Stores Officer', email='hse-stores-officer@example.com', role='hse')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')
    return user


def test_add_another_reopens_the_form_with_the_employee_department_and_date(app, client, db_session):
    _officer(app, client, db_session)
    amy = _person(db_session, 'Amy Again')
    dept = HseReference(kind='department', label='Stores Again', active=True)
    db_session.add_all([dept, HseReference(kind='ppe_type', label='Gloves', active=True)])
    db_session.flush()

    with app.test_request_context():
        url = url_for('hse.new_entry_form', register_key='ppe_register',
                      subject=amy.id, department=dept.id, entry_date='2026-09-10',
                      ppe_type='Gloves', due_at='2027-01-01')
    html = client.get(url).get_data(as_text=True)
    assert f'<option value="{amy.id}" selected' in html
    assert f'<option value="{dept.id}" selected' in html
    assert re.search(r'id="hse-f-entry_date"\s+value="2026-09-10"', html)
    assert 'id="hse-modal-save-another"' in html
    # Only the declared repeat fields carry over.
    assert re.search(r'id="hse-f-due_at"\s+value=""', html)
    assert '<option value="Gloves" selected' not in html


def test_add_another_is_offered_only_when_creating_a_ppe_entry(app, client, db_session):
    _officer(app, client, db_session)
    amy = _person(db_session, 'Amy Edit')
    entry = _ppe(db_session, amy, 'PPE-X1', 30)
    db_session.flush()
    with app.test_request_context():
        edit = url_for('hse.edit_entry_form', entry_id=entry.id)
        other = url_for('hse.new_entry_form', register_key='first_aid')
    assert 'hse-modal-save-another' not in client.get(edit).get_data(as_text=True)
    assert 'hse-modal-save-another' not in client.get(other).get_data(as_text=True)


# --- material request and tools -------------------------------------------

def test_a_material_request_has_a_unit_and_a_cost():
    fields = {f.name: f for f in MATERIAL_REQUEST.fields}
    assert (fields['unit'].type, fields['unit'].choices_kind) == ('choice', 'unit')
    assert fields['cost'].type == 'money'
    assert 'Cost (AED)' in columns(MATERIAL_REQUEST)


def test_a_material_requests_cost_is_stores_spend():
    rows = [SpendRow('material_request', TODAY, {'cost': '1,250.50'}),
            SpendRow('material_request', TODAY, {'qty_requested': 40})]
    assert spend_of(rows[0]) == Decimal('1250.50')
    assert spend_of(rows[1]) == 0, 'a quantity is not money'
    areas = {a['group']: a for a in spend_by_area(rows, date(2026, 1, 1), date(2026, 12, 31))['areas']}
    assert areas['stores']['amount'] == Decimal('1250.50')
    assert [r['key'] for r in areas['stores']['registers']] == ['material_request']


def test_a_tool_can_be_lost_which_is_red_but_not_open_work():
    assert 'Lost' in TOOLS_INVENTORY.statuses
    assert status_modifier('Lost') == 'poppy'
    assert 'Lost' not in OPEN_STATUSES
