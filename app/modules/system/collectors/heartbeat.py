"""Every minute (ovp-heartbeat.timer): call /healthz and save {ts, ok, ms}.
Kept light, with no Flask app: urllib and one INSERT. A minute with no row
reads as downtime."""
import sys
import time
import urllib.request
from datetime import datetime

import psycopg2

from config import Config
from app.modules.system.lib.notify import HEARTBEAT, notify

HEALTHZ_URL = 'http://127.0.0.1:5000/healthz'
HEALTHY_BODY = b'ok'
TIMEOUT_SECONDS = 5


def check(url=HEALTHZ_URL, timeout=TIMEOUT_SECONDS):
    """(ok, ms). Only a 200 with the healthy body within the timeout is up."""
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:
            ok = answer.status == 200 and answer.read(16) == HEALTHY_BODY
    except Exception:
        ok = False
    return ok, int((time.perf_counter() - started) * 1000)


def save(cur, ts, ok, ms):
    """Write one heartbeats row with `cur` and ping open admin pages; the caller commits."""
    cur.execute('INSERT INTO heartbeats (ts, ok, ms) VALUES (%s, %s, %s)', (ts, ok, ms))
    notify(cur, HEARTBEAT)


def main():
    ts = datetime.utcnow()
    ok, ms = check()
    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    try:
        with conn, conn.cursor() as cur:
            save(cur, ts, ok, ms)
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
