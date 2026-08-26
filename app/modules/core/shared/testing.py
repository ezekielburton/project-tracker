"""Shared pytest fixtures for the whole test suite.

Every module's tests reach these through the root conftest.py:
- `app`        builds the application once, on the dedicated test database.
- `client`     a Flask test HTTP client for that app.
- `db_session` wraps a single test in a transaction rolled back at teardown,
               so tests never persist data and stay isolated from one another.
"""
import pytest

from config import Config, TestingConfig
from app import create_app, db as _db


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
        yield application
        _db.session.remove()
        # Intentionally does NOT drop tables. The test database is dedicated and
        # per-test rollback already isolates data; dropping risks real data loss
        # if the URL were ever misconfigured.


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    connection = _db.engine.connect()
    transaction = connection.begin()
    _db.session.remove()
    _db.session.configure(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield _db.session
    finally:
        _db.session.remove()
        transaction.rollback()
        connection.close()
        _db.session.configure(bind=_db.engine)
