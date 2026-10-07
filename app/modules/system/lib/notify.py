"""Tells open admin pages that system data changed: one pg_notify on the
system_changes channel, sent inside the caller's transaction so it is only
delivered if the save commits."""
from app.modules.core.shared.services.live_events import SYSTEM_CHANGES_CHANNEL

SNAPSHOT, HEARTBEAT, JOBS = 'snapshot', 'heartbeat', 'jobs'


def notify(cur, what):
    cur.execute('SELECT pg_notify(%s, %s)', (SYSTEM_CHANGES_CHANNEL, what))
