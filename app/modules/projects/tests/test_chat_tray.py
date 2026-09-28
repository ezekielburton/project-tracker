"""Chat tray conversation list: visibility, unread counts, add/hide/pin,
ordering, and a flat query count. The thread is the overlay chat drawer.
"""
from datetime import datetime, timedelta

from flask import url_for

from app.modules.core.shared.models import (
    ChatTrayProject, Project, ProjectActivitySeen, ProjectNote, User,
)
from app.modules.core.shared.testing import count_queries, login_as


def _user(db_session, tag, role='cs'):
    user = User(name=f'Tray {tag}', email=f'chat-tray-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project(db_session, name, cs_lead):
    # created_by_id is NOT NULL in the database even though the model allows None.
    project = Project(name=name, cs_lead_id=cs_lead.id, created_by_id=cs_lead.id,
                      project_status='in_design')
    db_session.add(project)
    db_session.flush()
    return project


def _message(db_session, project, author, body, at=None):
    note = ProjectNote(project_id=project.id, author_id=author.id, body=body,
                       created_at=at or datetime.utcnow())
    db_session.add(note)
    db_session.flush()
    return note


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def _conversations(app, client):
    return client.get(_url(app, 'chat_tray.conversations')).get_json()


def test_your_own_projects_are_listed(app, client, db_session):
    owner = _user(db_session, 'owner')
    project = _project(db_session, 'Mars Snackation', owner)
    _message(db_session, project, owner, 'first message')
    login_as(client, app, owner, 'password123')

    rows = _conversations(app, client)['conversations']
    assert [r['project_id'] for r in rows] == [project.id]
    assert rows[0]['last_message']['text'] == 'first message'


def test_someone_elses_project_is_not_listed(app, client, db_session):
    owner = _user(db_session, 'other-owner')
    outsider = _user(db_session, 'outsider', 'designer')
    project = _project(db_session, 'Not Yours', owner)
    _message(db_session, project, owner, 'private')
    login_as(client, app, outsider, 'password123')

    assert _conversations(app, client)['conversations'] == []


def test_a_quiet_project_appears_only_once_pinned(app, client, db_session):
    owner = _user(db_session, 'pinner')
    project = _project(db_session, 'Quiet Project', owner)
    login_as(client, app, owner, 'password123')

    assert _conversations(app, client)['conversations'] == []

    client.post(_url(app, 'chat_tray.add_project'), json={'project_id': project.id})

    rows = _conversations(app, client)['conversations']
    assert [r['project_id'] for r in rows] == [project.id]
    assert rows[0]['added'] is True


def test_removing_drops_a_quiet_added_project_again(app, client, db_session):
    """Removing clears the manual add; the row survives to carry the hide."""
    owner = _user(db_session, 'unpinner')
    project = _project(db_session, 'Quiet Again', owner)
    login_as(client, app, owner, 'password123')

    client.post(_url(app, 'chat_tray.add_project'), json={'project_id': project.id})
    client.delete(_url(app, 'chat_tray.hide_project', project_id=project.id))

    assert _conversations(app, client)['conversations'] == []
    row = ChatTrayProject.query.filter_by(user_id=owner.id, project_id=project.id).first()
    assert row.added_at is None
    assert row.hidden_at is not None


def test_a_designer_cannot_pin_a_project_they_are_not_on(app, client, db_session):
    owner = _user(db_session, 'pin-owner')
    outsider = _user(db_session, 'pin-outsider', 'designer')
    project = _project(db_session, 'Off Limits', owner)
    login_as(client, app, outsider, 'password123')

    response = client.post(_url(app, 'chat_tray.add_project'), json={'project_id': project.id})
    assert response.status_code == 403


def test_management_can_pin_any_project(app, client, db_session):
    """Management can add any project (same rule as the chat post gate)."""
    owner = _user(db_session, 'boss-owner')
    boss = _user(db_session, 'boss', 'management')
    project = _project(db_session, 'Someone Elses', owner)
    login_as(client, app, boss, 'password123')

    response = client.post(_url(app, 'chat_tray.add_project'), json={'project_id': project.id})
    assert response.status_code == 200
    assert [r['project_id'] for r in _conversations(app, client)['conversations']] == [project.id]


def test_management_does_not_auto_surface_every_project(app, client, db_session):
    """Management's list only shows projects they are on or added."""
    owner = _user(db_session, 'quiet-owner')
    boss = _user(db_session, 'boss-list', 'management')
    project = _project(db_session, 'Busy Elsewhere', owner)
    _message(db_session, project, owner, 'not for the boss list')
    login_as(client, app, boss, 'password123')

    assert _conversations(app, client)['conversations'] == []


def test_unread_counts_other_peoples_messages_after_the_watermark(app, client, db_session):
    owner = _user(db_session, 'reader')
    mate = _user(db_session, 'writer', 'designer')
    project = _project(db_session, 'Counting', owner)

    db_session.add(ProjectActivitySeen(
        project_id=project.id, user_id=owner.id,
        last_seen_chat_at=datetime.utcnow() - timedelta(hours=1),
    ))
    db_session.flush()

    _message(db_session, project, mate, 'unread one')
    _message(db_session, project, mate, 'unread two')
    _message(db_session, project, owner, 'mine does not count')
    login_as(client, app, owner, 'password123')

    data = _conversations(app, client)
    assert data['conversations'][0]['unread'] == 2
    assert data['unread_total'] == 2


def test_newest_activity_sorts_to_the_top(app, client, db_session):
    owner = _user(db_session, 'sorter')
    older = _project(db_session, 'Older Talk', owner)
    newer = _project(db_session, 'Newer Talk', owner)
    _message(db_session, older, owner, 'a while ago', at=datetime.utcnow() - timedelta(days=2))
    _message(db_session, newer, owner, 'just now')
    login_as(client, app, owner, 'password123')

    rows = _conversations(app, client)['conversations']
    assert [r['project_id'] for r in rows] == [newer.id, older.id]


def test_the_thread_is_refused_outside_your_pool(app, client, db_session):
    owner = _user(db_session, 'thread-owner')
    outsider = _user(db_session, 'thread-outsider', 'designer')
    project = _project(db_session, 'Sealed', owner)
    _message(db_session, project, owner, 'private')
    login_as(client, app, outsider, 'password123')

    url = _url(app, 'chat_tray.project_thread', project_id=project.id)
    assert client.get(url).status_code == 403


def test_opening_a_thread_clears_the_unread(app, client, db_session):
    owner = _user(db_session, 'clearer')
    mate = _user(db_session, 'clearer-mate', 'designer')
    project = _project(db_session, 'Clearing', owner)
    _message(db_session, project, mate, 'unread')
    login_as(client, app, owner, 'password123')

    client.get(_url(app, 'chat_tray.project_thread', project_id=project.id))

    assert _conversations(app, client)['unread_total'] == 0


def test_the_list_does_not_grow_a_query_per_project(app, client, db_session):
    """Three projects and ten cost the same number of queries."""
    owner = _user(db_session, 'perf')
    mate = _user(db_session, 'perf-mate', 'designer')
    login_as(client, app, owner, 'password123')

    def _seed(count, prefix):
        for i in range(count):
            project = _project(db_session, f'{prefix} {i}', owner)
            _message(db_session, project, mate, f'message {i}')

    _seed(3, 'Small')
    with count_queries() as small:
        _conversations(app, client)

    _seed(7, 'Large')
    with count_queries() as large:
        _conversations(app, client)

    assert large[0] == small[0], f'query count grew with the list: {small[0]} -> {large[0]}'


def test_hiding_drops_a_conversation_from_the_list(app, client, db_session):
    owner = _user(db_session, 'hider')
    mate = _user(db_session, 'hider-mate', 'designer')
    project = _project(db_session, 'Too Noisy', owner)
    _message(db_session, project, mate, 'chatter')
    login_as(client, app, owner, 'password123')

    client.delete(_url(app, 'chat_tray.hide_project', project_id=project.id))

    assert _conversations(app, client)['conversations'] == []


def test_a_new_message_brings_a_hidden_conversation_back(app, client, db_session):
    owner = _user(db_session, 'unhider')
    mate = _user(db_session, 'unhider-mate', 'designer')
    project = _project(db_session, 'Back Again', owner)
    _message(db_session, project, mate, 'old chatter')
    login_as(client, app, owner, 'password123')

    client.delete(_url(app, 'chat_tray.hide_project', project_id=project.id))
    assert _conversations(app, client)['conversations'] == []

    _message(db_session, project, mate, 'something new')

    rows = _conversations(app, client)['conversations']
    assert [r['project_id'] for r in rows] == [project.id]


def test_a_pin_holds_a_conversation_above_newer_activity(app, client, db_session):
    owner = _user(db_session, 'pin-sorter')
    quiet = _project(db_session, 'Quiet But Pinned', owner)
    busy = _project(db_session, 'Busy', owner)
    _message(db_session, quiet, owner, 'ages ago', at=datetime.utcnow() - timedelta(days=3))
    _message(db_session, busy, owner, 'just now')
    login_as(client, app, owner, 'password123')

    assert [r['project_id'] for r in _conversations(app, client)['conversations']] == [busy.id, quiet.id]

    client.post(_url(app, 'chat_tray.pin_project', project_id=quiet.id), json={'pinned': True})

    rows = _conversations(app, client)['conversations']
    assert [r['project_id'] for r in rows] == [quiet.id, busy.id]
    assert rows[0]['pinned'] is True


def test_unpinning_returns_it_to_activity_order(app, client, db_session):
    owner = _user(db_session, 'unpin-sorter')
    quiet = _project(db_session, 'Quiet Once Pinned', owner)
    busy = _project(db_session, 'Busy Again', owner)
    _message(db_session, quiet, owner, 'ages ago', at=datetime.utcnow() - timedelta(days=3))
    _message(db_session, busy, owner, 'just now')
    login_as(client, app, owner, 'password123')

    client.post(_url(app, 'chat_tray.pin_project', project_id=quiet.id), json={'pinned': True})
    client.post(_url(app, 'chat_tray.pin_project', project_id=quiet.id), json={'pinned': False})

    assert [r['project_id'] for r in _conversations(app, client)['conversations']] == [busy.id, quiet.id]
