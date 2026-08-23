# app/sse_relay.py
#
# Per-worker in-memory pub/sub for SSE, bridging Postgres LISTEN/NOTIFY
# (cross-process) to local queues held by whichever worker has the relevant
# SSE connection open right now. One background greenlet per worker process
# holds a dedicated LISTEN connection — separate from the normal SQLAlchemy
# pool, since this one needs to sit idle indefinitely waiting for
# notifications, which isn't what a pooled request-scoped connection is for.
#
# Three subscription "topics":
#   - a specific project_id  (detail page SSE connections)
#   - the dashboard          (every project change matters here, since a
#                              project's tab membership can change; the
#                              client decides what to do with it, same as
#                              today's polling already does)
#   - a specific user_id     (notifications SSE connections)
#
# No locking around the subscriber dicts below — safe only because this
# runs under gevent's cooperative scheduling. A greenlet can only be
# switched out at an actual I/O wait point, and a plain dict/set mutation
# with no I/O in the middle can't be interrupted partway through. This
# would NOT be safe under real preemptive OS threads.

import os
import select
import time
import psycopg2
import psycopg2.extensions
from gevent import spawn
from gevent.queue import Queue

from app.live_events import PROJECT_CHANGES_CHANNEL, USER_NOTIFICATIONS_CHANNEL

_project_subscribers = {}      # project_id (int) -> set of Queue
_dashboard_subscribers = set()  # set of Queue
_user_subscribers = {}         # user_id (int) -> set of Queue


def subscribe_project(project_id):
    q = Queue()
    _project_subscribers.setdefault(project_id, set()).add(q)
    return q


def unsubscribe_project(project_id, q):
    subs = _project_subscribers.get(project_id)
    if subs:
        subs.discard(q)
        if not subs:
            _project_subscribers.pop(project_id, None)


def subscribe_dashboard():
    q = Queue()
    _dashboard_subscribers.add(q)
    return q


def unsubscribe_dashboard(q):
    _dashboard_subscribers.discard(q)


def subscribe_user(user_id):
    q = Queue()
    _user_subscribers.setdefault(user_id, set()).add(q)
    return q


def unsubscribe_user(user_id, q):
    subs = _user_subscribers.get(user_id)
    if subs:
        subs.discard(q)
        if not subs:
            _user_subscribers.pop(user_id, None)


def _dispatch_project_change(payload):
    try:
        project_id = int(payload)
    except (TypeError, ValueError):
        return
    targets = list(_project_subscribers.get(project_id, ())) + list(_dashboard_subscribers)
    for q in targets:
        q.put(project_id)


def _dispatch_user_notification(payload):
    try:
        user_id = int(payload)
    except (TypeError, ValueError):
        return
    for q in list(_user_subscribers.get(user_id, ())):
        q.put(user_id)


def _listen_loop(app):
    """Runs forever in a background greenlet, one per worker process.
    Reconnects automatically (after a short pause) if the DB connection
    drops for any reason — a network blip or a Postgres restart shouldn't
    permanently kill live updates until the next full app restart."""
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    while True:
        try:
            conn = psycopg2.connect(db_uri)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(f'LISTEN {PROJECT_CHANGES_CHANNEL};')
            cur.execute(f'LISTEN {USER_NOTIFICATIONS_CHANNEL};')
            # .warning() rather than .info() deliberately — Flask's app.logger
            # defaults to WARNING level outside debug mode, so an .info() call
            # here would be silently dropped in production even though the
            # relay started fine. This line is really an operational status
            # ping, not a true warning, but needs the higher severity to
            # actually show up in journalctl.
            app.logger.warning('SSE relay: LISTEN connection established.')

            while True:
                # select() on a psycopg2 connection blocks (cooperatively,
                # under gevent's monkey-patched select — see Stage 1) until
                # either the socket has data or the timeout elapses. The
                # timeout is just a periodic wake-up so this loop can
                # notice a dead connection reasonably promptly; it doesn't
                # need to do anything special when it fires empty-handed.
                select.select([conn], [], [], 30)
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    if notify.channel == PROJECT_CHANGES_CHANNEL:
                        _dispatch_project_change(notify.payload)
                    elif notify.channel == USER_NOTIFICATIONS_CHANNEL:
                        _dispatch_user_notification(notify.payload)
        except Exception as e:
            app.logger.warning(f'SSE relay: LISTEN connection dropped ({e}), reconnecting in 3s.')
            time.sleep(3)


def init_sse_relay(app):
    """Starts the background LISTEN greenlet for this worker process.
    Gated behind GEVENT_WORKER — same flag run.py uses for the gevent/
    psycopg2 patching — since this loop's cooperative blocking only
    behaves correctly once that patching is active. Under the plain local
    dev server (no gevent), this is a no-op: live updates simply don't
    run."""
    if os.environ.get('GEVENT_WORKER') == '1':
        spawn(_listen_loop, app)
