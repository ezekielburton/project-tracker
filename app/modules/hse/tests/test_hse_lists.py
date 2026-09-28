"""
Reference lists: tab layout, closed sets kept out, and idempotent quick-add
(reuse or revive an existing name, never a duplicate row).
"""
import runpy
from pathlib import Path

import psycopg2
from flask import url_for

from config import TestingConfig
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib import lists
from app.modules.hse.models import REFERENCE_KINDS, HseAsset


SERIAL_MIGRATION = (Path(__file__).resolve().parents[4]
                    / 'migrations' / 'add_hse_asset_serial.py')


def test_every_reference_kind_is_reachable_from_some_tab():
    """Every reference kind is editable from some tab."""
    reachable = set(lists.PROMINENT_KINDS) | set(lists.other_kinds())
    assert reachable == set(REFERENCE_KINDS)


def test_the_tab_strip_stays_short_as_registers_are_added():
    """The tab strip is fixed; extra kinds share the 'Other lists' tab."""
    keys = [t['key'] for t in lists.tabs()]
    assert keys == ['location', 'department', 'people', 'assets', 'other']


def test_a_kind_with_no_friendly_name_still_reads_properly():
    assert lists.kind_label('location') == 'Locations'
    assert lists.kind_label('ppe_category') == 'Ppe category'


def test_severity_and_status_are_not_editable_lists():
    """Severity and status are closed sets, never user-editable lists."""
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


def test_only_the_machines_section_offers_a_serial(app):
    with app.app_context():
        sections = {s['asset_kind']: s['has_serial'] for s in lists.panel_for('assets')}
    assert sections == {k: k in lists.SERIAL_ASSET_KINDS for k in sections}
    assert sections['machine'] is True


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
