"""Shared pytest fixtures for the whole test suite.

Every module's tests reach these through the root conftest.py:
- `app`        builds the application once, on the dedicated test database.
- `client`     a Flask test HTTP client for that app.
- `db_session` wraps a single test in a transaction rolled back at teardown,
               so tests never persist data and stay isolated from one another.
"""
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from config import Config, TestingConfig
from app import create_app, db as _db
from flask import url_for


@pytest.fixture(scope="session")
def app():
    uri = TestingConfig.SQLALCHEMY_DATABASE_URI
    assert uri, "TEST_DATABASE_URL is not set."
    dbname = uri.rsplit('/', 1)[-1].split('?')[0]
    assert 'test' in dbname.lower(), (
        f"Refusing to run: test database name {dbname!r} does not contain "
        "'test'. TEST_DATABASE_URL must point at a dedicated test database."
    )
    assert uri != Config.SQLALCHEMY_DATABASE_URI, (
        "Refusing to run: the test database URL equals the dev/prod "
        "DATABASE_URL. Point TEST_DATABASE_URL at a separate database."
    )
    application = create_app(TestingConfig)
    with application.app_context():
        _db.create_all()
    # Do NOT hold the app context open across `yield`: Flask reuses an
    # already-pushed app context for the same app instead of pushing a new
    # one per request, so an ambient context here would make every test
    # request in the whole run share one `flask.g` — and Flask-Login caches
    # the resolved user on `g._login_user`, so the first login anywhere in
    # the session would silently authenticate every request after it.
    yield application
    with application.app_context():
        _db.session.remove()
        # Intentionally does NOT drop tables. The test database is dedicated and
        # per-test rollback already isolates data; dropping risks real data loss
        # if the URL were ever misconfigured.


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    # Flask-SQLAlchemy's scoped session keys itself on the current app
    # context's identity, so every db_session.add()/.query() call — not
    # just the initial engine lookup — needs one active. Held open across
    # the whole test here is safe: this pushes a brand-new AppContext (and
    # g) per test function, unlike the `app` fixture's context above, which
    # would have been the SAME context for the entire session.
    #
    # session.configure(bind=connection, join_transaction_mode=...) alone
    # does NOT work here: Flask-SQLAlchemy's Session subclass overrides
    # get_bind() to resolve connections through its own engine registry,
    # which silently ignores that setting for actual query/commit traffic —
    # confirmed by writes becoming visible to a separate connection right
    # after a plain session.commit(), even though session_factory.kw showed
    # the right bind. Forcing get_bind() itself on the instance is what
    # actually pins every query to our connection; from there the standard
    # begin_nested()-plus-restart-listener recipe correctly contains each
    # commit() to a SAVEPOINT until the outer `transaction.rollback()` below
    # undoes everything at once.
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()
        _db.session.remove()
        _db.session.configure(bind=connection)
        session = _db.session()
        session.get_bind = lambda *a, **kw: connection
        session.begin_nested()

        def _restart_savepoint(sess, trans):
            if trans.nested and not trans._parent.nested:
                sess.begin_nested()

        event.listen(session, 'after_transaction_end', _restart_savepoint)
        try:
            yield _db.session
        finally:
            event.remove(session, 'after_transaction_end', _restart_savepoint)
            _db.session.remove()
            transaction.rollback()
            connection.close()
            _db.session.configure(bind=_db.engine)


def login_as(client, app, user, password):
    """Logs the test client in as `user` via the real /login route (not a
    session shortcut), so tests exercise actual auth. Returns the response
    of the login POST."""
    with app.test_request_context():
        login_url = url_for('auth.login')
    return client.post(
        login_url,
        data={'email': user.email, 'password': password},
        follow_redirects=True,
    )


@contextmanager
def count_queries():
    """Counts SQL statements executed against the test database while the
    block runs. Used for N+1 regression tests: seed a fixture at two
    different sizes and assert the query count doesn't grow with the
    fixture size, rather than asserting a fragile exact number.

    Listens on _db.session's current bind rather than _db.engine directly —
    the latter needs an app context to look up; callers always use this
    after the db_session fixture has already bound the session explicitly,
    so no app context is needed here either."""
    count = [0]

    def _before_cursor_execute(*args, **kwargs):
        count[0] += 1

    bind = _db.session.get_bind()
    event.listen(bind, 'before_cursor_execute', _before_cursor_execute)
    try:
        yield count
    finally:
        event.remove(bind, 'before_cursor_execute', _before_cursor_execute)