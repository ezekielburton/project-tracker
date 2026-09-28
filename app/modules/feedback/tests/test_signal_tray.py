"""Signal tray boards and Friction Log.

Key rule: everyone reads the Friction Log; only current champions, management
and admin can post.
"""
from datetime import timedelta

from flask import url_for

from app.modules.core.shared.lib.champions import CHAMPION_CARRY_OVER_WEEKS, week_start_for
from app.modules.core.shared.models import (
    BugReport, FeatureRequest, FrictionLogEntry, OvpChampion, User,
)
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role='designer'):
    user = User(name=f'Signal {tag}', email=f'signal-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _bug(db_session, author, title, status='in_queue', severity=None):
    bug = BugReport(title=title, description='...', submitted_by_id=author.id,
                    status=status, severity=severity)
    db_session.add(bug)
    db_session.flush()
    return bug


def _feature(db_session, author, title, status='requested'):
    feature = FeatureRequest(title=title, description='...', submitted_by_id=author.id,
                             status=status)
    db_session.add(feature)
    db_session.flush()
    return feature


def _url(app, endpoint):
    with app.test_request_context():
        return url_for(endpoint)


# ── Boards ─────────────────────────────────────────────────────────────────

def test_the_bug_board_returns_rows_and_chip_counts(app, client, db_session):
    author = _user(db_session, 'bug-author')
    _bug(db_session, author, 'Broken thing', severity='high')
    _bug(db_session, author, 'Other thing', status='resolved')
    login_as(client, app, author, 'password123')

    data = client.get(_url(app, 'signal_tray.bug_board')).get_json()
    titles = [r['title'] for r in data['rows']]
    assert 'Broken thing' in titles

    counts = {c['key']: c['count'] for c in data['counts']['by_status']}
    assert counts['resolved'] >= 1
    assert data['counts']['all'] == len(data['rows'])


def test_the_bug_board_reports_the_real_status_labels(app, client, db_session):
    author = _user(db_session, 'label-author')
    _bug(db_session, author, 'Labelled', status='fix_in_progress')
    login_as(client, app, author, 'password123')

    data = client.get(_url(app, 'signal_tray.bug_board')).get_json()
    row = [r for r in data['rows'] if r['title'] == 'Labelled'][0]
    assert row['status_label'] == 'Fix in progress'


def test_severity_comes_back_with_its_label(app, client, db_session):
    author = _user(db_session, 'sev-author')
    _bug(db_session, author, 'Severe', severity='high')
    login_as(client, app, author, 'password123')

    data = client.get(_url(app, 'signal_tray.bug_board')).get_json()
    row = [r for r in data['rows'] if r['title'] == 'Severe'][0]
    assert row['severity'] == 'high'
    assert row['severity_label'] == 'High'


def test_a_feature_awaiting_pickup_reads_as_queued_for_di(app, client, db_session):
    """Digital Innovation treats status 'requested' as its incoming tray."""
    author = _user(db_session, 'di-author')
    _feature(db_session, author, 'Waiting on DI', status='requested')
    _feature(db_session, author, 'Taken by DI', status='in_progress')
    login_as(client, app, author, 'password123')

    rows = {r['title']: r for r in client.get(_url(app, 'signal_tray.feature_board')).get_json()['rows']}
    assert rows['Waiting on DI']['di_state'] == 'queued'
    assert rows['Taken by DI']['di_state'] == 'picked_up'


# ── Friction Log ───────────────────────────────────────────────────────────

def test_everyone_can_read_the_friction_log(app, client, db_session):
    author = _user(db_session, 'friction-reader')
    login_as(client, app, author, 'password123')

    response = client.get(_url(app, 'signal_tray.friction_log'))
    assert response.status_code == 200
    assert response.get_json()['can_write'] is False


def test_a_plain_designer_cannot_post(app, client, db_session):
    login_as(client, app, _user(db_session, 'friction-designer'), 'password123')
    response = client.post(_url(app, 'signal_tray.post_friction'), json={'body': 'this is broken'})
    assert response.status_code == 403


def test_a_champion_of_any_department_can_post(app, client, db_session):
    champion = _user(db_session, 'friction-champion')
    db_session.add(OvpChampion(user_id=champion.id, department='production',
                               week_start=week_start_for()))
    db_session.flush()
    login_as(client, app, champion, 'password123')

    assert client.get(_url(app, 'signal_tray.friction_log')).get_json()['can_write'] is True
    assert client.post(_url(app, 'signal_tray.post_friction'),
                       json={'body': 'the handover step is slow'}).status_code == 200


def test_a_lapsed_champion_can_no_longer_post(app, client, db_session):
    lapsed = _user(db_session, 'friction-lapsed')
    stale = week_start_for() - timedelta(weeks=CHAMPION_CARRY_OVER_WEEKS + 1)
    db_session.add(OvpChampion(user_id=lapsed.id, department='finance',
                               week_start=stale))
    db_session.flush()
    login_as(client, app, lapsed, 'password123')

    assert client.get(_url(app, 'signal_tray.friction_log')).get_json()['can_write'] is False
    assert client.post(_url(app, 'signal_tray.post_friction'),
                       json={'body': 'still here?'}).status_code == 403


def test_management_can_post(app, client, db_session):
    login_as(client, app, _user(db_session, 'friction-boss', 'management'), 'password123')
    assert client.post(_url(app, 'signal_tray.post_friction'),
                       json={'body': 'reporting takes too long'}).status_code == 200


def test_an_empty_post_is_refused(app, client, db_session):
    login_as(client, app, _user(db_session, 'friction-empty', 'management'), 'password123')
    assert client.post(_url(app, 'signal_tray.post_friction'), json={'body': '   '}).status_code == 400


def test_entries_group_by_week_newest_first(app, client, db_session):
    boss = _user(db_session, 'friction-weeks', 'management')
    this_week = week_start_for()
    last_week = this_week - timedelta(weeks=1)
    db_session.add(FrictionLogEntry(author_id=boss.id, body='older', week_start=last_week))
    db_session.add(FrictionLogEntry(author_id=boss.id, body='newer', week_start=this_week))
    db_session.flush()
    login_as(client, app, boss, 'password123')

    weeks = client.get(_url(app, 'signal_tray.friction_log')).get_json()['weeks']
    assert weeks[0]['week_start'] == this_week.isoformat()
    assert weeks[1]['week_start'] == last_week.isoformat()


def test_an_entry_carries_its_authors_department(app, client, db_session):
    champion = _user(db_session, 'friction-dept')
    db_session.add(OvpChampion(user_id=champion.id, department='logistics',
                               week_start=week_start_for()))
    db_session.add(FrictionLogEntry(author_id=champion.id, body='vans are late',
                                    week_start=week_start_for()))
    db_session.flush()
    login_as(client, app, champion, 'password123')

    entry = client.get(_url(app, 'signal_tray.friction_log')).get_json()['weeks'][0]['entries'][0]
    assert entry['department'] == 'Logistics'


# ── The launcher bubble ────────────────────────────────────────────────────

def test_a_never_opened_tray_shows_no_bubble(app, client, db_session):
    """A user who never opened the tray gets 0, not the whole backlog."""
    author = _user(db_session, 'bubble-fresh')
    _bug(db_session, author, 'Something old')
    login_as(client, app, author, 'password123')

    assert client.get(_url(app, 'signal_tray.unread')).get_json()['unread'] == 0


def test_items_after_the_last_visit_count_and_opening_clears_them(app, client, db_session):
    author = _user(db_session, 'bubble-counter')
    login_as(client, app, author, 'password123')

    client.post(_url(app, 'signal_tray.mark_seen'))
    _bug(db_session, author, 'Filed after the visit')

    assert client.get(_url(app, 'signal_tray.unread')).get_json()['unread'] == 1

    client.post(_url(app, 'signal_tray.mark_seen'))
    assert client.get(_url(app, 'signal_tray.unread')).get_json()['unread'] == 0
