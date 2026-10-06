# Fires a Postgres NOTIFY for every watched project, DI project, notification
# recipient and Friction Log change in the current transaction. The single
# choke point for live updates: routes never announce changes themselves.
#
# Two hooks, because flushed objects drop out of session.new/dirty/deleted:
#   - before_flush (every flush) collects touched IDs into session.info.
#   - before_commit sends the NOTIFYs on the committing transaction;
#     Postgres delivers them only if it commits.
# SQLAlchemy runs before_commit BEFORE commit()'s own final flush, so
# before_commit flushes first; otherwise a change committed with no flush in
# between would never be collected.
#
# sse_relay.py LISTENs on these channels and wakes the SSE streams.

from sqlalchemy import event, text
from sqlalchemy.orm import Session

PROJECT_CHANGES_CHANNEL = 'project_changes'
USER_NOTIFICATIONS_CHANNEL = 'user_notifications'
DI_CHANGES_CHANNEL = 'di_changes'
FRICTION_CHANGES_CHANNEL = 'friction_changes'

# Watched models -> the project_id each change affects. Matched by class
# name so this file needn't import the models. A model missing here fires
# no live update at all.
_PROJECT_ID_GETTERS = {
    'Project':                lambda obj: obj.id,
    'ProjectCustomer':        lambda obj: obj.project_id,
    'Deliverable':            lambda obj: obj.project_id,
    'ProjectDesigner':        lambda obj: obj.project_id,
    'BriefFlag':              lambda obj: obj.project_id,
    'ProjectSubmission':      lambda obj: obj.project_id,
    'ProjectFile':            lambda obj: obj.project_id,
    'ProjectRegion':          lambda obj: obj.project_id,
    'ProjectRevision':        lambda obj: obj.project_id,
    # Secondary CS routes touch only these tables, so watch them directly.
    'ProjectSecondaryCS':       lambda obj: obj.project_id,
    'ProjectSecondaryCsRegion': lambda obj: obj.project_id,
    # Watched directly: a channel reset doesn't always touch a Deliverable.
    'ProjectPosmChannel':     lambda obj: obj.project_id,
    # No project_id of its own; hop through the deliverable.
    'DeliverableAssignment': lambda obj: obj.deliverable.project_id,
    # Decision-flag actions touch no other watched model, so watch them
    # directly. DecisionFlagMessage hops through its `flag` backref.
    'DecisionFlag':        lambda obj: obj.project_id,
    'DecisionFlagMessage': lambda obj: obj.flag.project_id,
    'ProjectNote': lambda obj: obj.project_id,
    'SiteVisit':   lambda obj: obj.project_id,
    # No project_id column of its own — relationship hop through .note.
    'ProjectNoteReaction': lambda obj: obj.note.project_id,
}

# Digital Innovation models -> the di_project_id (board) each change affects.
_DI_PROJECT_ID_GETTERS = {
    'DiProject':     lambda obj: obj.id,
    'DiFeature':     lambda obj: obj.di_project_id,
    'DiFeatureStep': lambda obj: obj.feature.di_project_id,
    'DiCostEntry':   lambda obj: obj.di_project_id,
    'DiIntakeItem':  lambda obj: obj.di_project_id,
    # Templates are department-wide. -1 is a sentinel (not 0: _collect_ids
    # skips falsy values) that reaches only the DI-wide dashboard subscribers.
    'DiStepTemplate': lambda obj: -1,
}


def _collect_ids(objects, seen, getters):
    for obj in objects:
        getter = getters.get(type(obj).__name__)
        if not getter:
            continue
        try:
            value = getter(obj)
        except Exception:
            # Object may be mid-deletion; never break a commit over a live update.
            continue
        if value:
            seen.add(value)


def _before_flush(session, flush_context, instances):
    project_ids = session.info.setdefault('_touched_project_ids', set())
    _collect_ids(session.new, project_ids, _PROJECT_ID_GETTERS)
    _collect_ids(session.dirty, project_ids, _PROJECT_ID_GETTERS)
    _collect_ids(session.deleted, project_ids, _PROJECT_ID_GETTERS)

    di_project_ids = session.info.setdefault('_touched_di_project_ids', set())
    _collect_ids(session.new, di_project_ids, _DI_PROJECT_ID_GETTERS)
    _collect_ids(session.dirty, di_project_ids, _DI_PROJECT_ID_GETTERS)
    _collect_ids(session.deleted, di_project_ids, _DI_PROJECT_ID_GETTERS)

    user_ids = session.info.setdefault('_touched_notification_user_ids', set())
    _collect_ids(session.new, user_ids, {'Notification': lambda obj: obj.recipient_id})

    # One channel for the whole Friction Log: a post added or deleted.
    if any(type(obj).__name__ == 'FrictionLogEntry'
           for obj in (*session.new, *session.deleted)):
        session.info['_friction_touched'] = True


def _before_commit(session):
    # No-op when clean; otherwise runs _before_flush so pending changes count.
    session.flush()

    project_ids = session.info.get('_touched_project_ids')
    if project_ids:
        for pid in project_ids:
            session.execute(
                text('SELECT pg_notify(:channel, :payload)'),
                {'channel': PROJECT_CHANGES_CHANNEL, 'payload': str(pid)}
            )
        # Clear so a later commit on this session doesn't re-announce them.
        session.info['_touched_project_ids'] = set()

    di_project_ids = session.info.get('_touched_di_project_ids')
    if di_project_ids:
        for did in di_project_ids:
            session.execute(
                text('SELECT pg_notify(:channel, :payload)'),
                {'channel': DI_CHANGES_CHANNEL, 'payload': str(did)}
            )
        session.info['_touched_di_project_ids'] = set()

    user_ids = session.info.get('_touched_notification_user_ids')
    if user_ids:
        for uid in user_ids:
            session.execute(
                text('SELECT pg_notify(:channel, :payload)'),
                {'channel': USER_NOTIFICATIONS_CHANNEL, 'payload': str(uid)}
            )
        session.info['_touched_notification_user_ids'] = set()

    if session.info.pop('_friction_touched', False):
        session.execute(
            text('SELECT pg_notify(:channel, :payload)'),
            {'channel': FRICTION_CHANGES_CHANNEL, 'payload': '1'}
        )


def init_live_events():
    """Register the hooks on the base Session class, so every session is
    covered. Called once from create_app()."""
    event.listen(Session, 'before_flush', _before_flush)
    event.listen(Session, 'before_commit', _before_commit)
