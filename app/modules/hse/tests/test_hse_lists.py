"""
Reference lists: tab layout, closed sets kept out, and idempotent quick-add
(reuse or revive an existing name, never a duplicate row).
"""
import importlib.util
import runpy
from pathlib import Path

import psycopg2
from flask import url_for

from config import TestingConfig
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib import lists
from app.modules.hse.models import ASSET_KINDS, REFERENCE_KINDS, HseAsset


SERIAL_MIGRATION = (Path(__file__).resolve().parents[4]
                    / 'migrations' / 'add_hse_asset_serial.py')


def test_every_list_has_one_address():
    """Each reference kind, asset kind and People opens at its own key, and
    no two share one."""
    keys = lists.list_keys()
    assert len(keys) == len(set(keys))
    assert set(keys) == set(REFERENCE_KINDS) | set(ASSET_KINDS) | {'people'}


def test_choice_lists_read_a_to_z():
    labels = [lists.kind_label(k) for k in lists.choice_kinds()]
    assert labels == sorted(labels)


def test_every_reference_list_feeds_some_register():
    """A list no register reads is dead weight on the page."""
    unused = [k for k in REFERENCE_KINDS if not lists.used_in(k)]
    assert unused == [], f'No register field is filled from: {unused}'


def test_a_kind_with_no_friendly_name_still_reads_properly():
    assert lists.kind_label('location') == 'Locations'
    assert lists.kind_label('ppe_category') == 'Ppe category'


def test_severity_and_status_are_not_editable_lists():
    """Severity and status are closed sets, never user-editable lists."""
    editable = set(lists.list_keys())
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
    """Quick-add reactivates a retired name instead of creating a duplicate row."""
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


# --- machine serial numbers -----------------------------------------------------

def _officer(app, client, db_session):
    user = User(name='HSE Lists Officer', email='hse-lists-officer@example.com', role='hse')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')


def test_an_asset_saves_and_edits_its_serial(app, client, db_session):
    _officer(app, client, db_session)
    with app.test_request_context():
        create = url_for('hse.create_asset')

    res = client.post(create, json={'kind': 'machine', 'label': 'Lists Press',
                                    'serial_no': '  SN-001 '})
    assert res.status_code == 201
    row = res.get_json()['row']
    assert row['serial_no'] == 'SN-001'

    with app.test_request_context():
        update = url_for('hse.update_asset', asset_id=row['id'])
    assert client.patch(update, json={'serial_no': 'SN-002'}).get_json()['row']['serial_no'] == 'SN-002'
    assert db_session.get(HseAsset, row['id']).serial_no == 'SN-002'

    # Blank clears it; an over-long one is refused and changes nothing.
    assert client.patch(update, json={'serial_no': ' '}).get_json()['row']['serial_no'] is None
    assert client.patch(update, json={'serial_no': 'x' * 121}).status_code == 400
    assert db_session.get(HseAsset, row['id']).serial_no is None


def test_only_machines_offer_a_serial(app):
    with app.app_context():
        views = {k: lists.list_view(k)['has_serial'] for k in ASSET_KINDS}
    assert views == {k: k in lists.SERIAL_ASSET_KINDS for k in ASSET_KINDS}


def test_an_empty_asset_list_is_flagged_and_retired_values_sit_apart(app, db_session):
    db_session.add(HseAsset(kind='forklift', label='Index Lift', active=False))
    db_session.flush()

    items = {i['key']: i for g in lists.index() for i in g['items']}
    assert items['forklift']['empty'] is True
    assert items['body_part']['empty'] is False, 'choice lists can be quick-added'

    view = lists.list_view('forklift')
    assert view['rows'] == [] and [r['label'] for r in view['retired']] == ['Index Lift']


def test_the_page_opens_a_list_and_old_tabs_still_land(app, client, db_session):
    _officer(app, client, db_session)
    with app.test_request_context():
        machine = url_for('hse.lists_page', list_key='machine')
        old = url_for('hse.lists_page', list_key='assets')
        vehicle = url_for('hse.lists_page', list_key='vehicle')
        missing = url_for('hse.lists_page', list_key='nope')

    assert client.get(machine).status_code == 200
    res = client.get(old)
    assert res.status_code == 302 and res.headers['Location'].endswith(vehicle)
    assert client.get(missing).status_code == 404


class _HeldConnection:
    """Defers the migration's commit and close to the test, so everything
    it does stays inside one transaction the test rolls back."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        pass

    def close(self):
        pass


def test_the_serial_migration_can_run_twice(app, monkeypatch):
    conn = psycopg2.connect(TestingConfig.SQLALCHEMY_DATABASE_URI)
    try:
        cur = conn.cursor()
        cur.execute("SET lock_timeout = '5s'")
        cur.execute('ALTER TABLE hse_assets DROP COLUMN IF EXISTS serial_no')
        # The script connects to its own URL; hand it the test transaction.
        monkeypatch.setattr(psycopg2, 'connect', lambda *a, **kw: _HeldConnection(conn))
        runpy.run_path(str(SERIAL_MIGRATION))
        runpy.run_path(str(SERIAL_MIGRATION))
        cur.execute("""
            SELECT data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'hse_assets' AND column_name = 'serial_no'
        """)
        assert cur.fetchall() == [('character varying', 120, 'YES')]
    finally:
        conn.rollback()
        conn.close()


# --- moving machine tags to the serial ------------------------------------

TAG_MOVE = Path(__file__).resolve().parents[4] / 'migrations' / 'move_machine_tags_to_serial.py'


def _load_tag_move():
    spec = importlib.util.spec_from_file_location('move_machine_tags_to_serial', TAG_MOVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_machine_tags_move_to_the_serial_and_the_move_is_safe_to_run_twice(db_session):
    tagged = HseAsset(kind='machine', label='Move CNC', ref='X1-1325T')
    placeholder = HseAsset(kind='machine', label='Move Bender', ref=' N/A ')
    both = HseAsset(kind='machine', label='Move Saw', ref='MC-03', serial_no='SCY25A030')
    vehicle = HseAsset(kind='vehicle', label='Move Figo', ref='T10413')
    db_session.add_all([tagged, placeholder, both, vehicle])
    db_session.flush()

    move = _load_tag_move()
    conn = db_session.connection().connection
    first = move.run(conn)
    assert first['moved'] >= 1 and first['cleared'] >= 1
    assert move.run(conn) == {'cleared': 0, 'moved': 0}

    db_session.expire_all()
    assert (tagged.ref, tagged.serial_no) == (None, 'X1-1325T')
    assert (placeholder.ref, placeholder.serial_no) == (None, None)
    assert (both.ref, both.serial_no) == ('MC-03', 'SCY25A030')
    assert (vehicle.ref, vehicle.serial_no) == ('T10413', None)
