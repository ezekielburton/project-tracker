# Per-worker pub/sub bridging Postgres LISTEN/NOTIFY to local SSE queues.
# One background greenlet per worker holds a dedicated LISTEN connection,
# outside the SQLAlchemy pool.
#
# Topics: one project, the dashboard (every project change), one user
# (notifications), one DI project, the DI dashboard (every DI change).
#
# No locks on the subscriber dicts: safe only under gevent's cooperative
# scheduling (no switch mid-mutation). NOT safe with real threads.

import os
import select
import time
import psycopg2
import psycopg2.extensions
from gevent import spawn
from gevent.queue import Queue

from app.modules.core.shared.services.live_events import PROJECT_CHANGES_CHANNEL, USER_NOTIFICATIONS_CHANNEL, DI_CHANGES_CHANNEL

_project_subscribers = {}      # project_id (int) -> set of Queue
_dashboard_subscribers = set()  # set of Queue
_user_subscribers = {}         # user_id (int) -> set of Queue
_di_project_subscribers = {}   # di_project_id (int) -> set of Queue
_di_dashboard_subscribers = set()  # set of Queue; DI screens not tied to one project


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


def subscribe_di_project(di_project_id):
    q = Queue()
    _di_project_subscribers.setdefault(di_project_id, set()).add(q)
    return q


def unsubscribe_di_project(di_project_id, q):
    subs = _di_project_subscribers.get(di_project_id)
    if subs:
        subs.discard(q)
        if not subs:
            _di_project_subscribers.pop(di_project_id, None)


def subscribe_di_dashboard():
    q = Queue()
    _di_dashboard_subscribers.add(q)
    return q


def unsubscribe_di_dashboard(q):
    _di_dashboard_subscribers.discard(q)


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


def _dispatch_di_change(payload):
    try:
        di_project_id = int(payload)
    except (TypeError, ValueError):
        return
    # Same dual dispatch as projects. The -1 template sentinel matches no
    # project key, so it reaches only the DI dashboard set.
    targets = list(_di_project_subscribers.get(di_project_id, ())) + list(_di_dashboard_subscribers)
    for q in targets:
        q.put(di_project_id)


def _listen_loop(app):
    """LISTEN and dispatch forever (one greenlet per worker). Reconnects
    after 3s if the connection drops."""
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    while True:
        conn = None
        try:
            conn = psycopg2.connect(db_uri)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(f'LISTEN {PROJECT_CHANGES_CHANNEL};')
            cur.execute(f'LISTEN {USER_NOTIFICATIONS_CHANNEL};')
            cur.execute(f'LISTEN {DI_CHANGES_CHANNEL};')
            # .warning so it reaches journalctl: app.logger drops .info outside debug.
            app.logger.warning('SSE relay: LISTEN connection established.')

            while True:
                # Cooperative under gevent's patched select. The 30s timeout
                # is just a periodic wake-up.
                select.select([conn], [], [], 30)
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    if notify.channel == PROJECT_CHANGES_CHANNEL:
                        _dispatch_project_change(notify.payload)
                    elif notify.channel == USER_NOTIFICATIONS_CHANNEL:
                        _dispatch_user_notification(notify.payload)
                    elif notify.channel == DI_CHANGES_CHANNEL:
                        _dispatch_di_change(notify.payload)
        except Exception as e:
            app.logger.warning(f'SSE relay: LISTEN connection dropped ({e}), reconnecting in 3s.')
            # Close the dead connection so reconnects don't leak sockets.
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            time.sleep(3)


def init_sse_relay(app):
    """Start this worker's LISTEN greenlet. Only when GEVENT_WORKER=1 (the
    flag run.py uses for gevent patching); otherwise a no-op and live
    updates don't run."""
    if os.environ.get('GEVENT_WORKER') == '1':
        spawn(_listen_loop, app)
