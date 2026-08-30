"""One-off tool: inspect (and optionally wipe) the dedicated test database.

Run from the repo root:
    python reset_test_db.py            # dry run — just reports row counts
    python reset_test_db.py --confirm  # actually truncates every table

Refuses to run against anything that isn't clearly the test database, using
the same checks the `app` pytest fixture uses (name must contain 'test',
and must differ from the dev/prod DATABASE_URL) — this only ever touches
TEST_DATABASE_URL, never DATABASE_URL.
"""
import sys

from config import Config, TestingConfig
from app import create_app, db


def _assert_safe_to_touch(uri):
    dbname = uri.rsplit('/', 1)[-1].split('?')[0]
    assert 'test' in dbname.lower(), (
        f"Refusing to run: test database name {dbname!r} does not contain 'test'."
    )
    assert uri != Config.SQLALCHEMY_DATABASE_URI, (
        "Refusing to run: TEST_DATABASE_URL equals the dev/prod DATABASE_URL."
    )


def main():
    confirm = '--confirm' in sys.argv

    uri = TestingConfig.SQLALCHEMY_DATABASE_URI
    assert uri, "TEST_DATABASE_URL is not set."
    _assert_safe_to_touch(uri)

    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        connection = db.engine.connect()

        tables = list(reversed(db.metadata.sorted_tables))
        print(f"Connected to: {uri}\n")
        counts = {}
        for table in tables:
            count = connection.execute(db.text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            counts[table.name] = count

        nonempty = {name: c for name, c in counts.items() if c}
        if not nonempty:
            print("Test database is already empty. Nothing to do.")
            connection.close()
            return

        print("Non-empty tables:")
        for name, c in sorted(nonempty.items(), key=lambda x: -x[1]):
            print(f"  {name}: {c} rows")

        if not confirm:
            print("\nDry run only — re-run with --confirm to truncate all tables.")
            connection.close()
            return

        print("\nTruncating all tables (CASCADE, restarting identities)...")
        table_names = ', '.join(f'"{t.name}"' for t in tables)
        connection.execute(db.text(f'TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE'))
        connection.commit()
        print("Done. Test database is now empty.")
        connection.close()


if __name__ == '__main__':
    main()
