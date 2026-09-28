# SSE "doorbell" streams: each only says "something changed" (queues from
# sse_relay.py). The client (polling.js / notifications.js) then re-fetches
# from the normal poll endpoints, which hold all visibility logic; pushing
# data here would duplicate it.
#
# Needs gevent workers (GEVENT_WORKER, run.py): under sync workers each open
# stream holds a whole worker.

from flask import Blueprint, Response
from flask_login import login_required
from gevent.queue import Empty

from app.modules.core.shared.services.sse_relay import (
    subscribe_project, unsubscribe_project,
    subscribe_dashboard, unsubscribe_dashboard,
    subscribe_user, unsubscribe_user,
    subscribe_di_project, unsubscribe_di_project,
    subscribe_di_dashboard, unsubscribe_di_dashboard,
)
from app.modules.core.shared.lib.capabilities import effective_user

sse_bp = Blueprint('sse', __name__, url_prefix='/sse')

# Keep-alive interval. SSE comment lines (':') are ignored by EventSource but
# stop Cloudflare Tunnel and other proxies closing an idle socket.
_HEARTBEAT_SECONDS = 5


def _event_stream(queue, unsubscribe):
    try:
        while True:
            try:
                payload = queue.get(timeout=_HEARTBEAT_SECONDS)
                yield f'data: {payload}\n\n'
            except Empty:
                yield ': keepalive\n\n'
    finally:
        # Runs when the client disconnects; without it dead queues pile up.
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


@sse_bp.route('/digital-innovation/<int:di_project_id>')
@login_required
def di_project_stream(di_project_id):
    q = subscribe_di_project(di_project_id)
    return _sse_response(_event_stream(q, lambda: unsubscribe_di_project(di_project_id, q)))


@sse_bp.route('/digital-innovation')
@login_required
def di_dashboard_stream():
    # DI screens not scoped to one project: Performance, Archive, Edit Templates.
    q = subscribe_di_dashboard()
    return _sse_response(_event_stream(q, lambda: unsubscribe_di_dashboard(q)))


@sse_bp.route('/notifications')
@login_required
def notifications_stream():
    # Emulation-aware: an admin emulating a user gets that user's stream.
    user_id = effective_user().id
    q = subscribe_user(user_id)
    return _sse_response(_event_stream(q, lambda: unsubscribe_user(user_id, q)))
