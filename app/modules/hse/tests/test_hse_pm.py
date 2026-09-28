"""
Preventive maintenance next due: parsed from the frequency label, only on
the latest entry per machine, shown in the table, the overlay and the
calendar. Computed at read time, never stored.
"""
from datetime import date

import pytest
from flask import url_for

from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as
from app.modules.hse.lib.calendar import drawer_cards, items_by_day, logged_items, pm_due_items
from app.modules.hse.lib.computed import interval_of, latest_by_asset, next_due
from app.modules.hse.lib.query import latest_ids
from app.modules.hse.lib.registers import MACHINE_PREVENTIVE
from app.modules.hse.lib.table import columns, row
from app.modules.hse.models import HseAsset, HseEntry


TODAY = date(2026, 9, 14)


class _Asset:
    def __init__(self, id, label):
        self.id, self.label = id, label


class _Entry:
    """Stands in for an HseEntry; lib code reads attributes only."""

    def __init__(self, id, entry_date, asset_id, frequency, register='machine_preventive',
                 ref=None, status='Working'):
        self.id, self.entry_date, self.asset_id = id, entry_date, asset_id
        self.register, self.status = register, status
        self.ref = ref or f'PM-{id:04d}'
        self.data = {'pm_frequency': frequency}
        self.asset = _Asset(asset_id, f'Machine {asset_id}')
        self.schedule_id = self.occurrence_date = self.due_at = None
        self.closed_at = self.created_by = self.created_at = None
        self.location = self.department = self.reported_by = None
        self.assigned_to = self.subject = self.waiting_on = self.waiting_since = None
        self.severity = None


# --- parsing --------------------------------------------------------------

@pytest.mark.parametrize('label, step', [
    ('Daily', (1, 0)), ('weekly', (7, 0)), ('Fortnightly', (14, 0)), ('Bi-weekly', (14, 0)),
    ('Monthly', (0, 1)), ('QUARTERLY', (0, 3)), ('6-monthly', (0, 6)),
    ('Half-yearly', (0, 6)), ('Semi-annual', (0, 6)), ('Biannual', (0, 6)),
    ('Annual', (0, 12)), ('Annually', (0, 12)), ('Yearly', (0, 12)), (' monthly ', (0, 1)),
])
def test_frequency_labels_are_read_whatever_their_case_or_dashes(label, step):
    assert interval_of(label) == step


@pytest.mark.parametrize('label', ['Emergency', 'Bi-monthly', '', None, 3])
def test_an_unrecognised_frequency_has_no_interval(label):
    assert interval_of(label) is None


def test_next_due_adds_the_interval_to_the_last_maintenance_date():
    assert next_due(_Entry(1, date(2026, 9, 1), 7, 'Weekly'), MACHINE_PREVENTIVE) == date(2026, 9, 8)
    assert next_due(_Entry(1, date(2026, 9, 1), 7, 'Quarterly'), MACHINE_PREVENTIVE) == date(2026, 12, 1)


def test_month_steps_clamp_to_a_short_month():
    assert next_due(_Entry(1, date(2026, 1, 31), 7, 'Monthly'), MACHINE_PREVENTIVE) == date(2026, 2, 28)
    assert next_due(_Entry(1, date(2027, 8, 31), 7, '6-monthly'), MACHINE_PREVENTIVE) == date(2028, 2, 29)


def test_an_emergency_job_has_no_next_due():
    assert next_due(_Entry(1, date(2026, 9, 1), 7, 'Emergency'), MACHINE_PREVENTIVE) is None


def test_the_latest_entry_per_machine_wins_ties_by_id():
    old = _Entry(1, date(2026, 6, 1), 7, 'Monthly')
    new = _Entry(2, date(2026, 9, 1), 7, 'Weekly')
    same_day = _Entry(3, date(2026, 9, 1), 7, 'Weekly')
    other = _Entry(4, date(2026, 1, 1), 8, 'Annual')
    latest = latest_by_asset([same_day, old, new, other])
    assert latest == {7: same_day, 8: other}


# --- the table ------------------------------------------------------------

def test_next_due_sits_right_after_the_frequency():
    heads = columns(MACHINE_PREVENTIVE)
    assert heads[heads.index('Frequency') + 1] == 'Next due'


def test_only_a_current_entry_shows_a_next_due_and_a_passed_one_reads_red():
    heads = columns(MACHINE_PREVENTIVE)
    at = heads.index('Next due')
    current = _Entry(2, date(2026, 9, 1), 7, 'Weekly')
    older = _Entry(1, date(2026, 6, 1), 7, 'Monthly')

    cell = row(current, MACHINE_PREVENTIVE, TODAY, current={2})[at]
    assert (cell['text'], cell['tone']) == ('08 Sep 2026', 'expired')
    assert row(older, MACHINE_PREVENTIVE, TODAY, current={2})[at]['kind'] == 'empty'
    ahead = _Entry(2, date(2026, 9, 10), 7, 'Monthly')
    assert row(ahead, MACHINE_PREVENTIVE, TODAY, current={2})[at]['tone'] is None


def test_latest_ids_picks_one_entry_per_machine(db_session):
    press = HseAsset(kind='machine', label='PM Press')
    saw = HseAsset(kind='machine', label='PM Saw')
    db_session.add_all([press, saw])
    db_session.flush()
    rows = [HseEntry(register='machine_preventive', ref=f'PMT-{i}', entry_date=d,
                     asset_id=a.id, status='Working', data={'pm_frequency': 'Monthly'})
            for i, (d, a) in enumerate([(date(2026, 5, 1), press), (date(2026, 8, 1), press),
                                        (date(2026, 7, 1), saw)])]
    db_session.add_all(rows)
    db_session.flush()
    assert latest_ids('machine_preventive') == {rows[1].id, rows[2].id}


def test_the_overlay_shows_next_due_read_only(app, client, db_session):
    user = User(name='PM Officer', email='hse-pm-officer@example.com', role='hse')
    user.set_password('password123')
    press = HseAsset(kind='machine', label='PM Overlay Press')
    db_session.add_all([user, press])
    db_session.flush()
    login_as(client, app, user, 'password123')
    old = HseEntry(register='machine_preventive', ref='PMO-1', entry_date=date(2026, 6, 1),
                   asset_id=press.id, status='Working', data={'pm_frequency': 'Monthly'})
    new = HseEntry(register='machine_preventive', ref='PMO-2', entry_date=date(2026, 9, 1),
                   asset_id=press.id, status='Working', data={'pm_frequency': 'Quarterly'})
    db_session.add_all([old, new])
    db_session.flush()

    def overlay(entry):
        with app.test_request_context():
            url = url_for('hse.edit_entry_form', entry_id=entry.id)
        return client.get(url).get_data(as_text=True)

    assert 'Next due 01 Dec 2026' in overlay(new)
    assert 'a later entry exists for this machine' in overlay(old)


# --- the calendar ---------------------------------------------------------

def test_the_calendar_draws_each_machines_next_due_once():
    entries = [_Entry(1, date(2026, 8, 1), 7, 'Monthly'),     # superseded
               _Entry(2, date(2026, 9, 7), 7, 'Weekly'),      # due 14 Sep
               _Entry(3, date(2026, 8, 10), 9, 'Monthly')]    # due 10 Sep, overdue
    items = pm_due_items(entries, date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert sorted((i['date'], i['state'], i['label']) for i in items) == [
        (date(2026, 9, 10), 'overdue', 'PM · Machine 9'),
        (date(2026, 9, 14), 'expiring', 'PM · Machine 7'),
    ]


def test_a_superseded_due_date_is_not_drawn():
    """The 1 Sep due date from the August entry is gone once a later PM is filed."""
    entries = [_Entry(1, date(2026, 8, 1), 7, 'Monthly'), _Entry(2, date(2026, 8, 20), 7, 'Annual')]
    assert pm_due_items(entries, date(2026, 9, 1), date(2026, 9, 30), TODAY) == []


def test_a_pm_entry_is_logged_on_its_date_and_due_on_the_next_without_double_counting():
    entry = _Entry(2, date(2026, 9, 7), 7, 'Weekly')
    grouped = items_by_day([], [entry], date(2026, 9, 1), date(2026, 9, 30), TODAY)
    assert [i['state'] for i in grouped[date(2026, 9, 7)]] == ['logged']
    assert [i['state'] for i in grouped[date(2026, 9, 14)]] == ['expiring']
    assert len(logged_items([entry], date(2026, 9, 1), date(2026, 9, 30))) == 1


def test_a_pm_due_card_offers_log_it_for_that_machine():
    entry = _Entry(3, date(2026, 8, 10), 9, 'Monthly', ref='PM-0003')
    grouped = items_by_day([], [entry], date(2026, 9, 10), date(2026, 9, 10), TODAY)
    card = drawer_cards(grouped[date(2026, 9, 10)], TODAY)[0]
    assert card['state'] == 'overdue'
    assert card['entry_id'] is None, 'no entry id, so the card shows Log it'
    assert (card['register'], card['asset_id']) == ('machine_preventive', 9)
    assert card['meta'] == 'Was due 10 Sep · 4 days overdue · last PM-0003'
    assert card['date'] == TODAY, 'the new PM is dated when it is logged'
