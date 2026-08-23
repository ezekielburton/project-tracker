# app/live_events.py
#
# Detects which projects (and which users, for notifications) were touched
# by the current database transaction, and fires a Postgres NOTIFY for each
# one right before that transaction commits. This is the single choke point
# for the whole SSE system — no route ever needs to remember to "announce"
# a change; if it touched one of the watched models, this catches it.
#
# Two-hook design, not one, because this codebase calls db.session.flush()
# constantly mid-request (to get auto-generated IDs before commit — see the
# DB Facts in CLAUDE.md). By the time a single end-of-transaction hook could
# look at session.new/dirty/deleted, anything already flushed earlier in the
# same request would already be gone from those collections — flushed
# objects become "clean" and drop out of session.dirty. So:
#
#   - before_flush fires on EVERY flush (an explicit one mid-request, or the
#     final implicit one at commit time) and accumulates touched IDs into
#     session.info, which persists for the whole life of the Session —
#     one request, under Flask-SQLAlchemy's scoped session.
#
#   - before_commit fires once, right before the transaction commits, and
#     is where we actually issue the NOTIFY — on the SAME session/
#     transaction that's about to commit. Postgres only delivers a NOTIFY
#     to listeners once the issuing transaction actually commits (and
#     silently drops it if the transaction rolls back instead), so doing
#     this before commit rather than after is both correct and avoids
#     needing a whole separate connection afterward.
#
# Stage 3 adds the per-worker background listener that actually LISTENs on
# these channels and dispatches to local SSE subscriber queues. This file
# only fires the NOTIFY — nothing is listening yet.

from sqlalchemy import event, text
from sqlalchemy.orm import Session

PROJECT_CHANGES_CHANNEL = 'project_changes'
USER_NOTIFICATIONS_CHANNEL = 'user_notifications'

# Models whose changes matter to the dashboard/detail SSE channel, and how
# to get from an instance of each to the project_id it affects. Matched by
# class name (not isinstance) so this file doesn't need to import every
# model — keeps it decoupled from app.models, avoiding import-order issues.
#
# ProjectFile, ProjectRegion and ProjectRevision are included here so that
# adding a reference file, adding a region, or sending a revision request
# actually fires a NOTIFY — without an entry here, api.py's fingerprint
# could widen all it wants and still never see these changes, since Stage 3
# would never even get told about them in the first place.
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
    # Secondary CS add/remove/region-subscription routes only ever touch
    # these two tables in isolation (no other model changes in the same
    # commit) — without entries here, those actions produced ZERO live
    # update signal, on any tab, ever.
    'ProjectSecondaryCS':       lambda obj: obj.project_id,
    'ProjectSecondaryCsRegion': lambda obj: obj.project_id,
    # POSM channel approval/reset routes often also touch Deliverable rows
    # in the same commit (already watched), so this worked by accident most
    # of the time — but not always (e.g. resetting a channel with no linked
    # deliverables). Watching it directly removes that fragility.
    'ProjectPosmChannel':     lambda obj: obj.project_id,
    # DeliverableAssignment has no project_id column of its own — it hangs
    # off a Deliverable, which does. Assigning a designer to a specific
    # deliverable (as opposed to the project-level ProjectDesigner) needs
    # this to be caught too, or "assignments down to the deliverable level"
    # would silently never trigger a live update.
    'DeliverableAssignment': lambda obj: obj.deliverable.project_id,
    # DecisionFlag is watched directly because raising, replying to, or
    # resolving one never touches any OTHER watched model in the same commit
    # (unlike POSM channels, which usually got a co-committed Deliverable
    # row), so without this no NOTIFY would fire for any decision-flag
    # action, for any viewer, including the acting user's own other open
    # tabs. DecisionFlagMessage has no
    # project_id column of its own (same shape as DeliverableAssignment
    # above) — it hangs off a DecisionFlag via the `flag` backref
    # (`messages = db.relationship('DecisionFlagMessage', backref='flag',
    # ...)` on DecisionFlag), which does.
    'DecisionFlag':        lambda obj: obj.project_id,
    'DecisionFlagMessage': lambda obj: obj.flag.project_id,
    'ProjectNote': lambda obj: obj.project_id,
    'SiteVisit':   lambda obj: obj.project_id,
    # No project_id column of its own — relationship hop through .note.
    'ProjectNoteReaction': lambda obj: obj.note.project_id,
}


def _collect_ids(objects, seen, getters):
    for obj in objects:
        getter = getters.get(type(obj).__name__)
        if not getter:
            continue
        try:
            value = getter(obj)
        except Exception:
            # Object could be mid-deletion or otherwise in an odd state —
            # skip it rather than risk crashing someone's commit over a
            # live-update side effect.
            continue
        if value:
            seen.add(value)


def _before_flush(session, flush_context, instances):
    project_ids = session.info.setdefault('_touched_project_ids', set())
    _collect_ids(session.new, project_ids, _PROJECT_ID_GETTERS)
    _collect_ids(session.dirty, project_ids, _PROJECT_ID_GETTERS)
    _collect_ids(session.deleted, project_ids, _PROJECT_ID_GETTERS)

    user_ids = session.info.setdefault('_touched_notification_user_ids', set())
    _collect_ids(session.new, user_ids, {'Notification': lambda obj: obj.recipient_id})


def _before_commit(session):
    project_ids = session.info.get('_touched_project_ids')
    if project_ids:
        for pid in project_ids:
            session.execute(
                text('SELECT pg_notify(:channel, :payload)'),
                {'channel': PROJECT_CHANGES_CHANNEL, 'payload': str(pid)}
            )
        # Clear so a second commit() within the same request (the
        # submission flow does this in a couple of places) doesn't
        # re-notify for IDs already announced, and nothing lingers into
        # whatever the next transaction on this same Session turns out to be.
        session.info['_touched_project_ids'] = set()

    user_ids = session.info.get('_touched_notification_user_ids')
    if user_ids:
        for uid in user_ids:
            session.execute(
                text('SELECT pg_notify(:channel, :payload)'),
                {'channel': USER_NOTIFICATIONS_CHANNEL, 'payload': str(uid)}
            )
        session.info['_touched_notification_user_ids'] = set()


def init_live_events():
    """Registers the before_flush/before_commit hooks above on SQLAlchemy's
    base Session class — called once from create_app(). Registering on the
    base class (rather than a specific instance) catches every session
    Flask-SQLAlchemy's scoped_session factory creates, app-wide."""
    event.listen(Session, 'before_flush', _before_flush)
    event.listen(Session, 'before_commit', _before_commit)
