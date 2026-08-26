# Thin streaming routes that tell the browser "something changed, go fetch"
# — they do NOT push data themselves. All the role-based visibility logic
# (who can see which projects, tab assignment, fingerprint diffing) lives in
# api.py's poll endpoints and in notifications.py's poll endpoint;
# duplicating any of it here would be a second place for it to drift out of
# sync. So each SSE endpoint below is just a doorbell: it blocks on a
# subscriber queue (see sse_relay.py) and emits a tiny SSE event whenever
# that queue gets something, and the client's polling.js / notifications.js
# fetch logic runs in response — driven by a push instead of a timer.
#
# Needs gevent workers to help at any scale — see run.py / GEVENT_WORKER. On
# the plain sync Flask dev server this works for a single connection (fine
# for local testing) but each open SSE stream would occupy one entire sync
# worker in production, defeating the point.

from flask import Blueprint, Response, session
from flask_login import login_required, current_user
from gevent.queue import Empty

from app.modules.core.shared.services.sse_relay import (
    subscribe_project, unsubscribe_project,
    subscribe_dashboard, unsubscribe_dashboard,
    subscribe_user, unsubscribe_user,
)

sse_bp = Blueprint('sse', __name__, url_prefix='/sse')

# How often to send a keep-alive comment when nothing's happened. SSE
# comment lines (start with ':') are invisible to EventSource's onmessage
# but keep the connection alive through Cloudflare Tunnel or any
# intermediate proxy that would otherwise time out an idle socket.
_HEARTBEAT_SECONDS = 20


def _event_stream(queue, unsubscribe):
    try:
        while True:
            try:
                payload = queue.get(timeout=_HEARTBEAT_SECONDS)
                yield f'data: {payload}\n\n'
            except Empty:
                yield ': keepalive\n\n'
    finally:
        # Runs when this generator is torn down — client closed the tab,
        # navigated away, or the connection otherwise died. Without this,
        # the subscriber registry would grow a dead queue for every closed
        # connection until the worker restarts.
        unsubscribe()


def _sse_response(generator):
    return Response(
        generator,
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # harmless if nothing buffers; prevents it if something does
            'Connection': 'keep-alive',
        },
    )


@sse_bp.route('/dashboard')
@login_required
def dashboard_stream():
    q = subscribe_dashboard()
    return _sse_response(_event_stream(q, lambda: unsubscribe_dashboard(q)))


@sse_bp.route('/projects/<int:project_id>')
@login_required
def project_stream(project_id):
    q = subscribe_project(project_id)
    return _sse_response(_event_stream(q, lambda: unsubscribe_project(project_id, q)))


@sse_bp.route('/notifications')
@login_required
def notifications_stream():
    # Emulation-aware actor pattern (see CLAUDE.md) — an admin emulating
    # another user should get a live stream of THAT user's notifications,
    # matching what /notifications/poll already shows them.
    emulating_id = session.get('emulating_user_id')
    user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id
    q = subscribe_user(user_id)
    return _sse_response(_event_stream(q, lambda: unsubscribe_user(user_id, q)))
