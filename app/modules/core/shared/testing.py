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
    # Do NOT hold an app context open across `yield`: Flask would reuse it
    # for every test request, so all requests would share one `g`. Flask-Login
    # caches the user on g._login_user, so the first login would then
    # authenticate every later request.
    yield application
    with application.app_context():
        _db.session.remove()
        # No drop_all: per-test rollback already isolates data, and dropping
        # risks real data loss if the URL is ever misconfigured.


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    # The scoped session is keyed on the app context, so every call needs one
    # active. A fresh context per test is safe to hold open (unlike `app`'s).
    #
    # session.configure(bind=connection) alone is NOT enough: Flask-SQLAlchemy's
    # get_bind() ignores it, so get_bind is overridden on the instance to pin
    # every query to this connection. Each commit() then lands in a SAVEPOINT
    # (restarted by the listener) and the outer rollback undoes it all.
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()
        _db.session.remove()
        _db.session.configure(bind=connection)
        session = _db.session()
        session.get_bind = lambda *a, **kw: connection
        fixture_savepoint = [session.begin_nested()]

        # Restart only the fixture's own SAVEPOINT: restarting one the app
        # opened (`with db.session.begin_nested():`) breaks its context manager.
        def _restart_savepoint(sess, trans):
            if trans is fixture_savepoint[0]:
                fixture_savepoint[0] = sess.begin_nested()

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
    """Log the test client in as `user` via the real /login route. Returns
    the login POST response."""
    with app.test_request_context():
        login_url = url_for('auth.login')
    return client.post(
        login_url,
        data={'email': user.email, 'password': password},
        follow_redirects=True,
    )


@contextmanager
def count_queries():
    """Count SQL statements run while the block executes. For N+1 tests:
    compare counts at two fixture sizes instead of asserting an exact number.
    Needs the db_session fixture (it listens on the session's bound connection)."""
    count = [0]

    def _before_cursor_execute(*args, **kwargs):
        count[0] += 1

    bind = _db.session.get_bind()
    event.listen(bind, 'before_cursor_execute', _before_cursor_execute)
    try:
        yield count
    finally:
        event.remove(bind, 'before_cursor_execute', _before_cursor_execute)