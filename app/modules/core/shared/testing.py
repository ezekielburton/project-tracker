"""

Shared pytest fixtures for the whole test suite.

Every module's tests reach these through the root confest.py:

- 'app' -       This builds the application once, on the dedidcated test database,
                and creates the schema (dropped again at the end of the run).
- 'client'      A flash test HTTP client for that app.
- 'db_session'  Wraps a single test in a transaction that is rolled back at teardown,
                so tests never persist data and stay isolated from one another.

"""

import pytest

from config import Config, TestingConfig
from app import create_app, db as _db

@pytest.fixture(scope="session")
def app():
    uri = TestingConfig.SQLALCHEMY_DATABASE_URI
    assert uri, "TEST_DATABASE_URL is not set."
    assert uri != Config.SQLALCHEMY_DATABASE_URI, (
        "Refusing to runL: the test database URL equals the dev/prod"
        "DATABASE_URL. Point TEST_DATABASE_URL at a seperate database."
    )
    application = create_app(TestingConfig)
    with application.app_context():
        _db.create_all()
        try:
            yield application
        finally:
            _db.session.remove()
            _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()

@pytest.fixture()
def db_session(app):
    connection = _db.engine.connect()
    transaction = connection.began()
    _db.session.remove()
    _db.session.configure(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield _db.session
    finally:
        _db.session.remove()
        transaction.rollback()
        connection.close()
        _db.session.configure(bind=_db.engine)

