"""
The entry overlay over HTTP: a time survives save and reopen, and the
machine registers carry each asset's serial on its option.
"""
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.models import HseAsset, HseEntry, HsePerson, HseReference


def _officer(app, client, db_session):
    user = User(name='HSE Routes Officer', email='hse-routes-officer@example.com', role='hse')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')
    return user


def _url(app, endpoint, **kw):
    with app.test_request_context():
        return url_for(endpoint, **kw)


def test_a_time_round_trips_through_save_and_reopen(app, client, db_session):
    _officer(app, client, db_session)
    trainer = HsePerson(name='Routes Trainer')
    db_session.add(trainer)
    db_session.flush()

    payload = {'entry_date': '2026-09-14', 'entry_time': '07:45', 'topic': 'Ladders',
               'performed_by': str(trainer.id), 'attendees': '12', 'status': 'Completed'}
    res = client.post(_url(app, 'hse.create_entry', register_key='toolbox_talk'), json=payload)
    assert res.status_code == 201, res.get_json()
    entry = db_session.get(HseEntry, res.get_json()['id'])
    assert entry.data['entry_time'] == '07:45'

    html = client.get(_url(app, 'hse.edit_entry_form', entry_id=entry.id)).get_data(as_text=True)
    assert '<input type="time" class="form-input" id="hse-f-entry_time" value="07:45">' in html

    res = client.patch(_url(app, 'hse.update_entry', entry_id=entry.id),
                       json=dict(payload, entry_time='7.45pm'))
    assert res.status_code == 400
    assert res.get_json()['errors'] == {'entry_time': 'Not a time — use HH:MM (24-hour)'}
    db_session.refresh(entry)
    assert entry.data['entry_time'] == '07:45', 'a refused edit writes nothing'


def test_a_machine_register_carries_each_assets_serial(app, client, db_session):
    _officer(app, client, db_session)
    press = HseAsset(kind='machine', label='Routes Press', serial_no='SN-4471')
    lathe = HseAsset(kind='machine', label='Routes Lathe')
    db_session.add_all([press, lathe])
    db_session.flush()

    html = client.get(_url(app, 'hse.new_entry_form', register_key='machine_maintenance',
                           asset=press.id)).get_data(as_text=True)
    assert f'<option value="{press.id}" selected data-serial="SN-4471">' in html
    assert f'<option value="{lathe.id}" data-serial="">' in html
    # The prefilled machine's serial is already showing before any change.
    assert 'Serial no. SN-4471' in html


def test_other_registers_leave_the_serial_off(app, client, db_session):
    _officer(app, client, db_session)
    html = client.get(_url(app, 'hse.new_entry_form', register_key='vehicle_inspection')
                      ).get_data(as_text=True)
    assert 'data-serial' not in html


def test_a_money_field_is_a_decimal_text_box_that_refuses_garbage(app, client, db_session):
    _officer(app, client, db_session)
    # Saving is refused while a required list is empty.
    db_session.add(HseReference(kind='expense_category', label='Course fees', active=True))
    db_session.flush()
    html = client.get(_url(app, 'hse.new_entry_form', register_key='training_expenses')
                      ).get_data(as_text=True)
    assert 'inputmode="decimal" class="form-input" id="hse-f-amount"' in html

    payload = {'entry_date': '2026-09-14', 'expense_category': 'Course fees',
               'amount': '-40'}
    res = client.post(_url(app, 'hse.create_entry', register_key='training_expenses'),
                      json=payload)
    assert res.status_code == 400
    assert res.get_json()['errors'] == {'amount': 'Enter an amount, e.g. 1,250.50'}

    res = client.post(_url(app, 'hse.create_entry', register_key='training_expenses'),
                      json=dict(payload, amount='AED 1,250.50'))
    assert res.status_code == 201, res.get_json()
    assert db_session.get(HseEntry, res.get_json()['id']).data['amount'] == '1250.50'
