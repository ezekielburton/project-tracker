"""Reads the collector's snapshot.json. A missing, broken or partial file reads
as empty, so pages show "No data" instead of failing."""
import json
from datetime import datetime, timedelta

STALE_AFTER = timedelta(minutes=15)


def read_snapshot(path=None):
    """The snapshot as a dict; {} when it can't be read."""
    if path is None:
        from flask import current_app
        path = current_app.config['SYSTEM_SNAPSHOT_PATH']
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_time(value):
    """A snapshot timestamp (ISO, naive UTC) as a datetime, or None."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def is_stale(snapshot, now=None):
    """True when there is no snapshot or it is older than STALE_AFTER."""
    taken = parse_time(snapshot.get('taken_at'))
    return taken is None or (now or datetime.utcnow()) - taken > STALE_AFTER
