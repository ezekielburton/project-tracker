import os

# Gevent + psycopg2 cooperative patching — ONLY when running under the
# production gunicorn gevent worker (GEVENT_WORKER=1 in that environment).
# Must happen before anything else imports psycopg2/SQLAlchemy, which is
# why this sits above `from app import create_app` rather than inside it.
# Local dev (python run.py, no env var set) is completely unaffected —
# this block is a no-op there, same behavior as today.
if os.environ.get('GEVENT_WORKER') == '1':
    from gevent import monkey
    monkey.patch_all()
    from psycogreen.gevent import patch_psycopg
    patch_psycopg()

from app import create_app


app = create_app()

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',  # listen on all interfaces, not just localhost
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
        threaded=True,  # one thread per request — without this, Werkzeug's dev
                         # server handles a single connection at a time, so one
                         # open SSE stream (which never closes) blocks every other
                         # tab/request until it disconnects. Only matters locally —
                         # Gunicorn in production never calls app.run() at all.
    )