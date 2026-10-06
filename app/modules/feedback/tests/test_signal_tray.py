"""Signal tray boards and Friction Log.

Key rule: everyone signed in reads and posts to the Friction Log.
"""
from datetime import timedelta

from flask import url_for

from app.modules.core.shared.models import BugReport, FeatureRequest, FrictionLogEntry, User
from app.modules.core.shared.testing import login_as
from app.modules.feedback.lib.friction import week_start_for


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

def _entry(db_session, author, body='too many clicks', week_start=None):
    entry = FrictionLogEntry(author_id=author.id, body=body,
                             week_start=week_start or week_start_for())
    db_session.add(entry)
    db_session.flush()
    return entry


def _delete_url(app, entry_id):
    with app.test_request_context():
        return url_for('signal_tray.delete_friction', entry_id=entry_id)


def _emulate(client, target):
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = target.id


def _entries(app, client):
    weeks = client.get(_url(app, 'signal_tray.friction_log')).get_json()['weeks']
    return [entry for week in weeks for entry in week['entries']]


def test_everyone_can_read_the_friction_log(app, client, db_session):
    login_as(client, app, _user(db_session, 'friction-reader'), 'password123')
    assert client.get(_url(app, 'signal_tray.friction_log')).status_code == 200


def test_a_plain_designer_can_post(app, client, db_session):
    author = _user(db_session, 'friction-designer')
    login_as(client, app, author, 'password123')
    response = client.post(_url(app, 'signal_tray.post_friction'), json={'body': 'too many clicks'})
    assert response.status_code == 200
    assert _entries(app, client)[-1]['author'] == author.name


def test_an_empty_post_is_refused(app, client, db_session):
    login_as(client, app, _user(db_session, 'friction-empty'), 'password123')
    assert client.post(_url(app, 'signal_tray.post_friction'), json={'body': '   '}).status_code == 400


def test_a_post_over_the_limit_is_refused(app, client, db_session):
    login_as(client, app, _user(db_session, 'friction-long'), 'password123')
    url = _url(app, 'signal_tray.post_friction')
    assert client.post(url, json={'body': 'x' * 501}).status_code == 400
    assert client.post(url, json={'body': 'x' * 500}).status_code == 200


def test_posts_read_oldest_first_with_the_newest_at_the_bottom(app, client, db_session):
    author = _user(db_session, 'friction-order')
    this_week = week_start_for()
    last_week = this_week - timedelta(weeks=1)
    _entry(db_session, author, 'older', last_week)
    _entry(db_session, author, 'first this week', this_week)
    _entry(db_session, author, 'latest', this_week)
    login_as(client, app, author, 'password123')

    weeks = client.get(_url(app, 'signal_tray.friction_log')).get_json()['weeks']
    assert [w['week_start'] for w in weeks][-2:] == [last_week.isoformat(), this_week.isoformat()]
    assert [e['body'] for e in weeks[-1]['entries']][-2:] == ['first this week', 'latest']


def test_a_post_carries_its_authors_department(app, client, db_session):
    designer = _user(db_session, 'friction-dept')
    boss = _user(db_session, 'friction-boss', 'management')
    _entry(db_session, designer, 'designer post')
    _entry(db_session, boss, 'boss post')
    login_as(client, app, designer, 'password123')

    by_body = {e['body']: e for e in _entries(app, client)}
    assert by_body['designer post']['department'] == 'Design'
    assert by_body['boss post']['department'] == 'Management'


def test_only_your_own_posts_are_marked_deletable(app, client, db_session):
    me = _user(db_session, 'friction-me')
    other = _user(db_session, 'friction-other')
    _entry(db_session, me, 'mine')
    _entry(db_session, other, 'theirs')
    login_as(client, app, me, 'password123')

    by_body = {e['body']: e for e in _entries(app, client)}
    assert by_body['mine']['can_delete'] is True
    assert by_body['theirs']['can_delete'] is False


def test_an_author_deletes_their_own_post(app, client, db_session):
    author = _user(db_session, 'friction-own-delete')
    entry = _entry(db_session, author)
    login_as(client, app, author, 'password123')

    assert client.delete(_delete_url(app, entry.id)).status_code == 200
    assert entry.id not in [e['id'] for e in _entries(app, client)]


def test_deleting_someone_elses_post_is_refused(app, client, db_session):
    entry = _entry(db_session, _user(db_session, 'friction-victim'))
    login_as(client, app, _user(db_session, 'friction-intruder'), 'password123')
    assert client.delete(_delete_url(app, entry.id)).status_code == 403


def test_an_admin_deletes_any_post(app, client, db_session):
    entry = _entry(db_session, _user(db_session, 'friction-any'))
    login_as(client, app, _user(db_session, 'friction-admin', 'admin'), 'password123')
    assert client.delete(_delete_url(app, entry.id)).status_code == 200


def test_deleting_an_unknown_post_is_not_found(app, client, db_session):
    login_as(client, app, _user(db_session, 'friction-unknown', 'admin'), 'password123')
    assert client.delete(_delete_url(app, 999999)).status_code == 404


def test_an_emulating_admin_posts_as_the_emulated_person(app, client, db_session):
    admin = _user(db_session, 'friction-emu-admin', 'admin')
    target = _user(db_session, 'friction-emu-target')
    login_as(client, app, admin, 'password123')
    _emulate(client, target)

    client.post(_url(app, 'signal_tray.post_friction'), json={'body': 'posted while emulating'})
    by_body = {e['body']: e for e in _entries(app, client)}
    assert by_body['posted while emulating']['author'] == target.name


def test_an_emulating_admin_deletes_only_as_the_emulated_person(app, client, db_session):
    admin = _user(db_session, 'friction-emu-del-admin', 'admin')
    target = _user(db_session, 'friction-emu-del-target')
    entry = _entry(db_session, _user(db_session, 'friction-emu-del-other'))
    login_as(client, app, admin, 'password123')
    _emulate(client, target)

    assert client.delete(_delete_url(app, entry.id)).status_code == 403


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
