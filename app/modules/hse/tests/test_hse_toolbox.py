"""
Toolbox talks carry a status: only a Completed talk (or one with no status,
filed before statuses existed) counts as held, for schedule coverage and
for training delivered. Attendees are required only for a Completed talk.
"""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

from app.modules.hse.lib.calendar import logged_items
from app.modules.hse.lib.forms import ValidationError, apply_payload, form_fields
from app.modules.hse.lib.metrics import training_delivered
from app.modules.hse.lib.overview import this_week
from app.modules.hse.lib.query import OPEN_STATUSES
from app.modules.hse.lib.registers import TOOLBOX_TALK, counts_as_done
from app.modules.hse.lib.schedule import coverage
from app.modules.hse.lib.table import columns
from app.modules.hse.models import HseEntry


TODAY = date(2026, 9, 14)
BACKFILL = Path(__file__).resolve().parents[4] / 'migrations' / 'backfill_toolbox_status.py'


class _Talk:
    """Stands in for an HseEntry; the lib code reads attributes only."""

    def __init__(self, status, day=date(2026, 9, 9), attendees=10, schedule_id=None,
                 occurrence_date=None, register='toolbox_talk'):
        self.id = id(self)
        self.register, self.status, self.entry_date = register, status, day
        self.data = {'attendees': attendees, 'topic': 'Ladders'}
        self.schedule_id, self.occurrence_date = schedule_id, occurrence_date
        self.asset_id = self.asset = self.closed_at = self.due_at = None
        self.ref = 'TBT-0001'


class _Schedule:
    id, register, label, frequency, interval = 9, 'toolbox_talk', 'Weekly talk', 'weekly', 1
    weekday, day_of_month, active, ends_on, assets = 2, None, True, None, []
    starts_on = date(2026, 9, 1)


class _Stub:
    def __init__(self):
        self.data = {}
        for name in ('entry_date', 'status', 'location_id', 'department_id',
                     'reported_by_id', 'ref', 'id'):
            setattr(self, name, None)


PAYLOAD = {'entry_date': '2026-09-14', 'topic': 'Ladders', 'reported_by': '2'}


# --- the declaration ------------------------------------------------------

def test_a_talk_is_scheduled_completed_or_cancelled_and_none_of_them_is_open():
    assert TOOLBOX_TALK.status_source == 'stored'
    assert TOOLBOX_TALK.statuses == ('Scheduled', 'Completed', 'Cancelled')
    assert TOOLBOX_TALK.default_status == 'Completed'
    assert not set(TOOLBOX_TALK.statuses) & set(OPEN_STATUSES)


def test_a_talk_has_no_days_open_column():
    assert 'Days open' not in columns(TOOLBOX_TALK)
    assert columns(TOOLBOX_TALK)[-1] == 'Status'


# --- the form -------------------------------------------------------------

def test_a_completed_talk_needs_its_attendees():
    with pytest.raises(ValidationError) as err:
        apply_payload(_Stub(), TOOLBOX_TALK, dict(PAYLOAD, status='Completed'))
    assert err.value.errors == {'attendees': 'Required when the status is Completed'}


@pytest.mark.parametrize('status', ['Scheduled', 'Cancelled'])
def test_a_talk_not_yet_held_can_leave_attendees_blank(status):
    entry = apply_payload(_Stub(), TOOLBOX_TALK, dict(PAYLOAD, status=status))
    assert entry.status == status
    assert entry.data['attendees'] is None


def test_a_talk_still_needs_a_status():
    with pytest.raises(ValidationError) as err:
        apply_payload(_Stub(), TOOLBOX_TALK, dict(PAYLOAD, attendees='5'))
    assert err.value.errors == {'status': 'Required'}


def test_the_form_stars_attendees_only_while_completed(db_session):
    def attendees(fields):
        return next(f for f in fields if f['name'] == 'attendees')

    new = attendees(form_fields(TOOLBOX_TALK))
    assert (new['required'], new['required_when'], new['required_now']) == (
        False, 'Completed', True), 'a new talk defaults to Completed'
    scheduled = HseEntry(register='toolbox_talk', status='Scheduled', data={})
    assert attendees(form_fields(TOOLBOX_TALK, scheduled))['required_now'] is False


# --- counting -------------------------------------------------------------

def test_only_a_completed_or_legacy_talk_counts_as_done():
    assert counts_as_done(_Talk('Completed'))
    assert counts_as_done(_Talk(None))
    assert not counts_as_done(_Talk('Scheduled'))
    assert not counts_as_done(_Talk('Cancelled'))
    assert counts_as_done(_Talk('Scheduled', register='machine_maintenance')), \
        'registers without a done status are unaffected'


@pytest.mark.parametrize('status, done', [
    ('Completed', 1), (None, 1), ('Scheduled', 0), ('Cancelled', 0)])
def test_only_a_held_talk_ticks_off_its_occurrence(status, done):
    talk = _Talk(status, schedule_id=9, occurrence_date=date(2026, 9, 9))
    cov = coverage([_Schedule()], [talk], date(2026, 9, 9), date(2026, 9, 9), TODAY)
    assert (cov['due'], cov['done']) == (1, done)


def test_training_sessions_count_only_held_talks():
    talks = [_Talk('Completed', attendees=10), _Talk(None, attendees=4),
             _Talk('Scheduled', attendees=None), _Talk('Cancelled', attendees=8)]
    delivered = training_delivered(talks, date(2026, 9, 1), date(2026, 9, 30))
    assert (delivered['sessions'], delivered['attendees']) == (2, 14)


def test_the_weekly_figures_count_only_held_talks():
    talks = [_Talk('Completed'), _Talk('Scheduled'), _Talk('Cancelled')]
    week = this_week([], talks, date(2026, 9, 7), date(2026, 9, 13), TODAY)
    assert week['trainings'] == 1


def test_a_talk_not_held_is_not_drawn_as_logged_work():
    talks = [_Talk('Completed'), _Talk('Scheduled'), _Talk('Cancelled'), _Talk(None)]
    assert len(logged_items(talks, date(2026, 9, 1), date(2026, 9, 30))) == 2


# --- the data script ------------------------------------------------------

def _load_backfill():
    spec = importlib.util.spec_from_file_location('backfill_toolbox_status', BACKFILL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_backfill_completes_legacy_talks_and_is_safe_to_run_twice(db_session):
    legacy = HseEntry(register='toolbox_talk', ref='TBB-1', entry_date=TODAY, data={})
    planned = HseEntry(register='toolbox_talk', ref='TBB-2', entry_date=TODAY,
                       status='Scheduled', data={})
    other = HseEntry(register='vehicle_mileage', ref='TBB-3', entry_date=TODAY, data={})
    db_session.add_all([legacy, planned, other])
    db_session.flush()

    backfill = _load_backfill()
    conn = db_session.connection().connection
    assert backfill.run(conn) >= 1
    assert backfill.run(conn) == 0
    db_session.expire_all()
    assert (legacy.status, planned.status, other.status) == ('Completed', 'Scheduled', None)
