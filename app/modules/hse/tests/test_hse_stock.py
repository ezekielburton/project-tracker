"""
Materials in stock: one line per material, movements in data['moves'] and
the balance computed from them at read time. Also the movement route, the
duplicate-material check and the merge script for the old snapshot rows.
"""
import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib import stock
from app.modules.hse.lib.forms import ValidationError, apply_payload
from app.modules.hse.lib.registers import MATERIALS_IN_STOCK
from app.modules.hse.lib.table import columns, row
from app.modules.hse.models import HseAttachment, HseEntry


TODAY = date(2026, 9, 14)
MERGE = Path(__file__).resolve().parents[4] / 'migrations' / 'merge_stock_rows.py'


class _Line:
    def __init__(self, opening=10, moves=(), reorder=None, unit='Box', entry_date=TODAY, **extra):
        self.id, self.ref, self.register = 1, 'HSM-0001', 'materials_in_stock'
        self.entry_date = entry_date
        self.data = dict({'item': 'Gloves', 'opening_stock': opening, 'unit': unit,
                          'reorder_level': reorder, 'moves': list(moves)}, **extra)
        for name in ('status', 'severity', 'closed_at', 'due_at', 'location',
                     'department', 'asset', 'reported_by', 'assigned_to', 'subject',
                     'performed_by'):
            setattr(self, name, None)


def move(day, kind, qty, **kw):
    return dict({'date': day, 'kind': kind, 'qty': qty}, **kw)


# --- the balance ----------------------------------------------------------

def test_the_balance_applies_movements_in_date_order_whatever_order_they_were_saved():
    line = _Line(opening=10, moves=[
        move('2026-09-10', 'issued', 3),
        move('2026-09-01', 'received', 5),
        move('2026-09-05', 'count', 20),      # resets to 20 before the issue
    ])
    assert stock.balance(line) == 17


def test_a_count_overrides_everything_before_it():
    line = _Line(opening=10, moves=[move('2026-09-01', 'received', 100),
                                    move('2026-09-02', 'count', 0)])
    assert stock.balance(line) == 0


def test_same_day_movements_keep_the_order_they_were_recorded():
    line = _Line(opening=5, moves=[move('2026-09-01', 'count', 8),
                                   move('2026-09-01', 'issued', 2)])
    assert stock.balance(line) == 6


def test_a_line_with_no_movements_is_its_opening_stock():
    assert stock.balance(_Line(opening=12)) == 12
    assert stock.balance_text(_Line(opening=12)) == '12 Box'
    assert stock.balance_text(_Line(opening=12, unit=None)) == '12'


def test_an_unmerged_snapshot_still_counts_its_received_and_issued():
    """Rows the merge script has not reached keep their old closing stock."""
    assert stock.balance(_Line(opening=10, received=6, issued=4)) == 12


def test_low_stock_is_at_or_below_the_reorder_level():
    assert stock.is_low_stock(_Line(opening=5, reorder=5))
    assert not stock.is_low_stock(_Line(opening=6, reorder=5))
    assert not stock.is_low_stock(_Line(opening=0, reorder=None)), 'no level, never low'


def test_history_is_newest_first_with_who_recorded_it():
    line = _Line(moves=[move('2026-09-01', 'received', 5, by_id=7, note='Delivery'),
                        move('2026-09-03', 'issued', 2, by_id=None)])
    rows = stock.history(line, {7: 'S. Pillai'})
    assert [(r['date'], r['label'], r['qty'], r['by']) for r in rows] == [
        (date(2026, 9, 3), 'Issued', 2, None),
        (date(2026, 9, 1), 'Received', 5, 'S. Pillai')]
    assert rows[1]['note'] == 'Delivery'


# --- recording a movement -------------------------------------------------

def test_a_movement_is_appended_with_who_recorded_it():
    line = _Line(opening=10)
    stock.add_move(line, {'kind': 'received', 'date': '2026-09-14', 'qty': '4',
                          'note': ' Delivery '}, by_id=3, today=TODAY)
    assert line.data['moves'] == [{'date': '2026-09-14', 'kind': 'received', 'qty': 4,
                                   'note': 'Delivery', 'by_id': 3}]
    assert stock.balance(line) == 14


@pytest.mark.parametrize('payload, errors', [
    ({'kind': 'stolen', 'date': '2026-09-14', 'qty': 1}, {'kind'}),
    ({'kind': 'received', 'date': 'soon', 'qty': 1}, {'date'}),
    ({'kind': 'received', 'date': '2026-09-15', 'qty': 1}, {'date'}),
    ({'kind': 'received', 'date': '2026-09-14', 'qty': 0}, {'qty'}),
    ({'kind': 'issued', 'date': '2026-09-14', 'qty': -2}, {'qty'}),
    ({'kind': 'issued', 'date': '2026-09-14', 'qty': '1.5'}, {'qty'}),
    ({'kind': 'count', 'date': '2026-09-14', 'qty': -1}, {'qty'}),
    ({'kind': 'received', 'date': '2026-09-14', 'qty': 1, 'note': 'x' * 201}, {'note'}),
])
def test_a_bad_movement_is_refused_and_writes_nothing(payload, errors):
    line = _Line()
    with pytest.raises(ValidationError) as err:
        stock.add_move(line, payload, by_id=1, today=TODAY)
    assert set(err.value.errors) == errors
    assert line.data['moves'] == []


def test_a_count_of_zero_is_allowed():
    line = _Line(opening=4)
    stock.add_move(line, {'kind': 'count', 'date': '2026-09-01', 'qty': 0}, 1, TODAY)
    assert stock.balance(line) == 0


# --- the table ------------------------------------------------------------

def test_the_table_shows_the_balance_and_marks_low_stock():
    heads = columns(MATERIALS_IN_STOCK)
    assert heads == ['Ref', 'Material', 'Category', 'Stored at', 'Reorder level', 'Balance']
    cell = row(_Line(opening=3, reorder=5), MATERIALS_IN_STOCK, TODAY)[heads.index('Balance')]
    assert (cell['text'], cell['tone']) == ('3 Box', 'low')


def test_the_old_snapshot_fields_are_gone_from_the_form():
    names = [f.name for f in MATERIALS_IN_STOCK.fields]
    assert names == ['item', 'material_category', 'unit', 'location', 'reorder_level',
                     'opening_stock', 'entry_date', 'reported_by', 'assigned_to']


# --- one line per material ------------------------------------------------

def _stock_row(db_session, ref, item, **data):
    entry = HseEntry(register='materials_in_stock', ref=ref, entry_date=TODAY,
                     data=dict({'item': item, 'opening_stock': 1}, **data))
    db_session.add(entry)
    db_session.flush()
    return entry


PAYLOAD = {'item': 'Nitrile gloves', 'opening_stock': '10', 'entry_date': '2026-09-14'}


def test_a_second_line_for_the_same_material_is_refused(db_session):
    _stock_row(db_session, 'HSD-1', 'Nitrile Gloves ')
    fresh = HseEntry(register='materials_in_stock')
    with pytest.raises(ValidationError) as err:
        apply_payload(fresh, MATERIALS_IN_STOCK, dict(PAYLOAD, item='  nitrile gloves'))
    assert err.value.errors['item'].startswith('Already on HSD-1')


def test_a_line_can_be_saved_again_under_its_own_name(db_session):
    line = _stock_row(db_session, 'HSD-2', 'Nitrile gloves', moves=[move('2026-09-01', 'issued', 1)])
    apply_payload(line, MATERIALS_IN_STOCK, dict(PAYLOAD, reorder_level='4'))
    assert line.data['reorder_level'] == 4
    assert line.data['moves'], 'editing the line keeps its movements'


def test_a_different_material_is_fine(db_session):
    _stock_row(db_session, 'HSD-3', 'Nitrile gloves')
    apply_payload(HseEntry(register='materials_in_stock'), MATERIALS_IN_STOCK,
                  dict(PAYLOAD, item='Latex gloves'))


# --- the movement route ---------------------------------------------------

def _officer(app, client, db_session, role='hse', email='hse-stock-officer@example.com'):
    user = User(name='Stock Officer', email=email, role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')
    return user


def _move_url(app, entry_id):
    with app.test_request_context():
        return url_for('hse.record_move', entry_id=entry_id)


def test_the_route_records_a_movement_and_returns_the_new_balance(app, client, db_session):
    user = _officer(app, client, db_session)
    line = _stock_row(db_session, 'HSR-1', 'Route gloves', unit='Box', reorder_level=5)
    today = date.today().isoformat()

    res = client.post(_move_url(app, line.id), json={'kind': 'issued', 'date': today, 'qty': '1'})
    assert res.status_code == 200, res.get_json()
    assert res.get_json() == {'id': line.id, 'balance': 0, 'balance_text': '0 Box', 'low': True}
    db_session.refresh(line)
    assert line.data['moves'][-1]['by_id'] == user.id


def test_the_route_refuses_a_bad_movement_with_field_errors(app, client, db_session):
    _officer(app, client, db_session)
    line = _stock_row(db_session, 'HSR-2', 'Route boots')
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    res = client.post(_move_url(app, line.id), json={'kind': 'received', 'date': tomorrow, 'qty': 0})
    assert res.status_code == 400
    assert set(res.get_json()['errors']) == {'date', 'qty'}
    db_session.refresh(line)
    assert 'moves' not in line.data


def test_the_route_only_takes_stock_lines(app, client, db_session):
    _officer(app, client, db_session)
    other = HseEntry(register='toolbox_talk', ref='HSR-3', entry_date=TODAY, data={})
    db_session.add(other)
    db_session.flush()
    res = client.post(_move_url(app, other.id),
                      json={'kind': 'received', 'date': TODAY.isoformat(), 'qty': 1})
    assert res.status_code == 404


def test_the_route_needs_manage_hse(app, client, db_session):
    _officer(app, client, db_session, role='management', email='hse-stock-viewer@example.com')
    line = _stock_row(db_session, 'HSR-4', 'Route vests')
    res = client.post(_move_url(app, line.id),
                      json={'kind': 'received', 'date': TODAY.isoformat(), 'qty': 1})
    assert res.status_code == 403
    db_session.refresh(line)
    assert 'moves' not in line.data


def test_the_overlay_lists_the_movements(app, client, db_session):
    user = _officer(app, client, db_session)
    line = _stock_row(db_session, 'HSR-5', 'Route masks', unit='Pack', moves=[
        move('2026-09-01', 'received', 12, note='First delivery', by_id=user.id)])
    with app.test_request_context():
        url = url_for('hse.edit_entry_form', entry_id=line.id)
    html = client.get(url).get_data(as_text=True)
    assert 'Stock movements' in html
    assert 'First delivery' in html and 'Stock Officer' in html
    assert '13 Pack' in html


# --- the merge script -----------------------------------------------------

def _load_merge():
    spec = importlib.util.spec_from_file_location('merge_stock_rows', MERGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snapshot(db_session, ref, day, item, opening, received=None, issued=None, **data):
    entry = HseEntry(register='materials_in_stock', ref=ref, entry_date=day,
                     data=dict({'item': item, 'opening_stock': opening,
                                'received': received, 'issued': issued}, **data))
    db_session.add(entry)
    db_session.flush()
    return entry


def test_the_merge_folds_snapshots_into_one_line_and_is_safe_to_run_twice(db_session):
    first = _snapshot(db_session, 'MRG-1', date(2026, 1, 5), 'Merge Gloves', 10, 5, 3,
                      unit='Box', reorder_level=4)
    # Opens at 12, the running balance, so no count is needed.
    second = _snapshot(db_session, 'MRG-2', date(2026, 2, 5), ' merge gloves', 12, 0, 2,
                       material_category='PPE')
    # Opens at 7 where the ledger says 10: a count comes first.
    third = _snapshot(db_session, 'MRG-3', date(2026, 3, 5), 'MERGE GLOVES', 7, 4, None,
                      unit='Pack')
    alone = _snapshot(db_session, 'MRG-4', date(2026, 1, 1), 'Merge Boots', 3, 1, 1)
    db_session.add(HseAttachment(entry_id=third.id, filename='f.pdf', original_filename='f.pdf',
                                 file_type='pdf', nas_path='/HSE/x/f.pdf'))
    db_session.flush()
    ids = (first.id, second.id, third.id, alone.id)

    merge = _load_merge()
    conn = db_session.connection().connection
    merge.run(conn)
    again = merge.run(conn)
    db_session.expire_all()

    rows = HseEntry.query.filter(HseEntry.id.in_(ids)).all()
    assert sorted(r.ref for r in rows) == ['MRG-1', 'MRG-4']
    line = db_session.get(HseEntry, first.id)
    assert [(m['date'], m['kind'], m['qty']) for m in line.data['moves']] == [
        ('2026-01-05', 'received', 5), ('2026-01-05', 'issued', 3),
        ('2026-02-05', 'issued', 2),
        ('2026-03-05', 'count', 7), ('2026-03-05', 'received', 4)]
    assert line.data['opening_stock'] == 10
    assert stock.balance(line) == 11
    assert (line.data['unit'], line.data['material_category'], line.data['reorder_level']) == (
        'Pack', 'PPE', 4), 'the latest non-empty values carry over'
    assert 'received' not in line.data and 'issued' not in line.data
    assert [a.entry_id for a in HseAttachment.query.filter_by(nas_path='/HSE/x/f.pdf')] == [first.id]

    boots = db_session.get(HseEntry, alone.id)
    assert stock.balance(boots) == 3
    assert 'received' not in boots.data

    assert (again['merged'], again['moves'], again['counts']) == (0, 0, 0)
