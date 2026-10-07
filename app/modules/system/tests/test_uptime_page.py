"""Uptime from the heartbeat: a gap between beats, a failed beat and a silent
heartbeat now are all downtime; downtime right after a deploy is planned; the
30 day-blocks, the summary, and adding an incident note."""
from datetime import date, datetime, timedelta

import pytest

from app.modules.system.models import DeployRun, Heartbeat, SystemIncident
from app.modules.system.services import uptime

NOW = datetime(2031, 3, 4, 10, 0, 0)  # 14:00 in Dubai


def _beats(db_session, minutes_ago, ok=True):
    for minutes in minutes_ago:
        db_session.add(Heartbeat(ts=NOW - timedelta(minutes=minutes), ok=ok, ms=10))
    db_session.flush()


def _steady(db_session, start, end=0, skip=()):
    """A beat every minute from `start` minutes ago to `end`, leaving out `skip`."""
    _beats(db_session, [m for m in range(start, end - 1, -1) if m not in skip])


def test_a_gap_between_beats_is_downtime(db_session):
    _steady(db_session, 120, skip=range(51, 61))  # nothing from 60 to 51 minutes ago
    found = uptime.outages(NOW)
    assert len(found) == 1
    assert found[0]['start'] == NOW - timedelta(minutes=60)
    assert found[0]['end'] == NOW - timedelta(minutes=50)
    assert found[0]['minutes'] == 10 and not found[0]['planned'] and not found[0]['ongoing']


def test_one_late_beat_is_not_downtime(db_session):
    _steady(db_session, 30, skip=(10,))  # a 2-minute gap is a slow timer, not an outage
    assert uptime.outages(NOW) == []


def test_failed_beats_are_downtime_and_join_up(db_session):
    _steady(db_session, 30, skip=(20, 19, 18))
    _beats(db_session, (20, 19, 18), ok=False)
    found = uptime.outages(NOW)
    assert [(o['start'], o['end']) for o in found] == [(NOW - timedelta(minutes=21), NOW - timedelta(minutes=18))]


def test_a_silent_heartbeat_now_is_downtime_still_going(db_session):
    _steady(db_session, 60, end=8)
    found = uptime.outages(NOW)
    assert found[-1]['ongoing'] and found[-1]['end'] == NOW and found[-1]['minutes'] == 7
    assert uptime.summary({}, NOW)['ongoing']


def test_downtime_right_after_a_deploy_is_planned(db_session):
    _steady(db_session, 240, skip=list(range(200, 204)) + list(range(100, 104)))
    db_session.add(DeployRun(ran_at=NOW - timedelta(minutes=210), tag='v2.7', migrations_applied=1,
                             duration_ms=40_000, ok=True))
    db_session.flush()
    planned = [o['planned'] for o in uptime.outages(NOW)]
    assert planned == [True, False]
    assert uptime.summary({}, NOW)['incidents'] == 1


def test_summary_reads_percent_minutes_restart_and_deploy(db_session):
    _steady(db_session, 1000, skip=range(500, 510))
    db_session.add(DeployRun(ran_at=NOW - timedelta(days=3), tag='v2.6.4', migrations_applied=2,
                             duration_ms=48_000, ok=True))
    db_session.flush()
    started = int((NOW - timedelta(days=42, hours=7) - datetime(1970, 1, 1)).total_seconds())
    found = uptime.summary({'workers': {'started_at': started}}, NOW)
    assert found['down_minutes'] == 10 and found['pct'] == 99.0
    assert found['since_restart']['days'] == 42 and found['since_restart']['hours'] == 7
    assert found['deploy']['tag'] == 'v2.6.4' and found['deploy']['ago'] == '3 days ago'


def test_with_no_heartbeats_there_is_no_reading(db_session):
    found = uptime.summary({}, NOW)
    assert found['pct'] is None and found['incidents'] == 0 and found['deploy'] is None
    assert {day['state'] for day in uptime.days(NOW)} == {'grey'}


def test_day_blocks(db_session):
    # Beats for the last 3 days; today has an unplanned gap, yesterday a planned one.
    _steady(db_session, 3 * 1440, skip=list(range(60, 70)) + list(range(1440 + 60, 1440 + 64)))
    db_session.add(DeployRun(ran_at=NOW - timedelta(minutes=1440 + 66), tag='v2.7', migrations_applied=0,
                             duration_ms=1, ok=True))
    db_session.flush()
    blocks = uptime.days(NOW)
    assert len(blocks) == 30 and blocks[-1]['day'] == date(2031, 3, 4)
    assert [b['state'] for b in blocks[-4:]] == ['green', 'green', 'amber', 'red']
    assert blocks[0]['state'] == 'grey'


def test_deploy_history_newest_first(db_session):
    for days_ago, tag in ((5, 'v2.6'), (1, 'v2.7')):
        db_session.add(DeployRun(ran_at=NOW - timedelta(days=days_ago), tag=tag, migrations_applied=1,
                                 duration_ms=31_000, ok=True))
    db_session.flush()
    assert [row['tag'] for row in uptime.deploys(NOW)][:2] == ['v2.7', 'v2.6']
    assert uptime.deploys(NOW)[0]['duration'] == '31.0 s'


def test_adding_an_incident(db_session):
    uptime.add_incident('Server unreachable', '26', 'Power cut in the server room.', '2031-03-01', None,
                        today=date(2031, 3, 4))
    db_session.flush()
    saved = SystemIncident.query.filter_by(title='Server unreachable').one()
    assert saved.minutes == 26 and saved.happened_on == date(2031, 3, 1)
    assert uptime.incidents()[0] == {'title': 'Server unreachable', 'minutes': 26,
                                     'note': 'Power cut in the server room.', 'date': '1 Mar'}


@pytest.mark.parametrize('title, minutes, happened_on, message', [
    ('', None, None, 'Add a title'),
    ('x' * 121, None, None, 'Keep the title under 120 characters'),
    ('Outage', 'ten', None, 'Minutes must be a whole number'),
    ('Outage', -3, None, 'Minutes must be a whole number'),
    ('Outage', None, 'yesterday', 'Pick a date'),
    ('Outage', None, '2031-03-05', 'The date can’t be in the future'),
])
def test_an_incident_needs_a_title_whole_minutes_and_a_past_date(db_session, title, minutes, happened_on, message):
    with pytest.raises(uptime.IncidentError, match=message):
        uptime.add_incident(title, minutes, None, happened_on, None, today=date(2031, 3, 4))


def test_an_incident_without_minutes_note_or_date_is_today(db_session):
    incident = uptime.add_incident('  Planned restart  ', '', '  ', None, None, today=date(2031, 3, 4))
    assert (incident.title, incident.minutes, incident.note, incident.happened_on) == \
        ('Planned restart', None, None, date(2031, 3, 4))
