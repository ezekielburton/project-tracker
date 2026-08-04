import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subprocess
from urllib.parse import urlparse, urlunparse
from app import create_app
from app.nas import download_app_file

# The backup created by backup_db.py's last successful run.
# Update this if you want to test-restore a different backup file.
NAS_BACKUP_PATH = "/Admin/Database/2026/Week 30/Monday 20 July Backup.dump"
LOCAL_DUMP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "restore_test.dump")
TEST_DB_NAME = "project_tracker_restore_test"

flask_app = create_app()
with flask_app.app_context():
    print(f"Downloading {NAS_BACKUP_PATH} from NAS...")
    file_bytes = download_app_file(NAS_BACKUP_PATH)
    with open(LOCAL_DUMP_PATH, "wb") as f:
        f.write(file_bytes)
    print(f"Saved {len(file_bytes)} bytes to {LOCAL_DUMP_PATH}")

    db_url = flask_app.config['SQLALCHEMY_DATABASE_URI']
    parsed = urlparse(db_url)

    # Point at a throwaway scratch DB instead of the real one
    test_db_url = urlunparse(parsed._replace(path=f"/{TEST_DB_NAME}"))
    # No dbname at all (the 'postgres' maintenance DB) — needed to run
    # CREATE DATABASE / DROP DATABASE, since you can't do that on the DB
    # you're currently connected to.
    admin_db_url = urlunparse(parsed._replace(path="/postgres"))

    print(f"Dropping old '{TEST_DB_NAME}' if it exists...")
    subprocess.run(
        ["psql", admin_db_url, "-c", f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}";'],
        capture_output=True
    )

    print(f"Creating scratch database '{TEST_DB_NAME}'...")
    result = subprocess.run(
        ["psql", admin_db_url, "-c", f'CREATE DATABASE "{TEST_DB_NAME}";'],
        capture_output=True
    )
    if result.returncode != 0:
        print("CREATE DATABASE failed:", result.stderr.decode())
        sys.exit(1)

    print("Restoring dump into scratch database...")
    result = subprocess.run(
        ["pg_restore", "--no-owner", "--dbname", test_db_url, LOCAL_DUMP_PATH],
        capture_output=True
    )
    # pg_restore often exits non-zero on harmless notices (e.g. an extension
    # already existing) — print stderr as info rather than treating it as fatal.
    stderr_text = result.stderr.decode()
    if stderr_text:
        print("pg_restore messages:\n" + stderr_text)

    print("Verifying data landed correctly...")
    check = subprocess.run(
        ["psql", test_db_url, "-t", "-c",
         "SELECT (SELECT COUNT(*) FROM users), (SELECT COUNT(*) FROM projects);"],
        capture_output=True
    )
    out = check.stdout.decode().strip()
    err = check.stderr.decode().strip()
    if err:
        print("Row count check failed:", err)
    else:
        print("Row counts (users, projects):", out)

    print(f"\nRestore test complete. Scratch DB '{TEST_DB_NAME}' left in place for inspection.")
    print(f"Drop it when you're done with: psql \"{admin_db_url}\" -c 'DROP DATABASE \"{TEST_DB_NAME}\";'")
