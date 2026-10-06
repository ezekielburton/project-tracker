"""live_events.py: a change followed straight by commit() (no flush or
query in between) must still send its NOTIFY inside that commit."""
from contextlib import contextmanager
from datetime import date

from sqlalchemy import event

from app import db
from app.modules.core.shared.services.live_events import DI_CHANGES_CHANNEL, FRICTION_CHANGES_CHANNEL
from app.modules.core.shared.models import FrictionLogEntry, User
from app.modules.digital_innovation.models import DiStepTemplate


@contextmanager
def _capture_notifies():
    sent = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if 'pg_notify' in statement:
            sent.append((parameters['channel'], parameters['payload']))

    bind = db.session.get_bind()
    event.listen(bind, 'before_cursor_execute', _before_cursor_execute)
    try:
        yield sent
    finally:
        event.remove(bind, 'before_cursor_execute', _before_cursor_execute)


def test_add_then_immediate_commit_sends_the_notify(db_session):
    with _capture_notifies() as sent:
        db_session.add(DiStepTemplate(stage='researching', title='New', sort_order=0))
        db_session.commit()
    assert (DI_CHANGES_CHANNEL, '-1') in sent


def test_edit_then_immediate_commit_sends_the_notify(db_session):
    template = DiStepTemplate(stage='researching', title='Old', sort_order=0)
    db_session.add(template)
    db_session.commit()

    with _capture_notifies() as sent:
        template.title = 'Renamed'
        db_session.commit()
    assert (DI_CHANGES_CHANNEL, '-1') in sent


def test_commit_with_nothing_touched_sends_no_notify(db_session):
    with _capture_notifies() as sent:
        db_session.commit()
    assert sent == []


def _friction_author(db_session, tag):
    user = User(name=f'Live Friction {tag}', email=f'live-friction-{tag}@example.com', role='designer')
    user.set_password('password123')
    db_session.add(user)
    db_session.commit()
    return user


def test_a_new_friction_post_rings_the_friction_channel(db_session):
    author = _friction_author(db_session, 'post')
    with _capture_notifies() as sent:
        db_session.add(FrictionLogEntry(author_id=author.id, body='slow', week_start=date.today()))
        db_session.commit()
    assert (FRICTION_CHANGES_CHANNEL, '1') in sent


def test_deleting_a_friction_post_rings_the_friction_channel(db_session):
    author = _friction_author(db_session, 'delete')
    entry = FrictionLogEntry(author_id=author.id, body='slow', week_start=date.today())
    db_session.add(entry)
    db_session.commit()

    with _capture_notifies() as sent:
        db_session.delete(entry)
        db_session.commit()
    assert (FRICTION_CHANGES_CHANNEL, '1') in sent
