#!/usr/bin/env python3
"""
migrate.py — Vitamin Helix migration runner

Usage:
  python3 migrate.py           # Run all pending migrations
  python3 migrate.py --seed    # Mark all existing migrations as applied (run once on first setup)
  python3 migrate.py --status  # Show which migrations have and haven't been applied
"""

import os
import sys
import subprocess
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(override=True)

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), 'migrations')


def get_connection():
    url = os.environ.get('DATABASE_URL')
    if not url:
        print("ERROR: DATABASE_URL not found in environment.")
        sys.exit(1)
    return psycopg2.connect(url)


def ensure_tracking_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id          SERIAL PRIMARY KEY,
                filename    VARCHAR(255) UNIQUE NOT NULL,
                applied_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    conn.commit()


def get_applied(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY applied_at;")
        return {row[0] for row in cur.fetchall()}


def record_applied(conn, filename):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT DO NOTHING;",
            (filename,)
        )
    conn.commit()


def get_all_scripts():
    return sorted([
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith('.py') and not f.startswith('_')
    ])


def cmd_status(conn):
    applied = get_applied(conn)
    scripts = get_all_scripts()
    print(f"{'Script':<45} {'Status'}")
    print("-" * 55)
    for s in scripts:
        status = "applied" if s in applied else "PENDING"
        print(f"{s:<45} {status}")


def cmd_seed(conn):
    scripts = get_all_scripts()
    applied = get_applied(conn)
    seeded = 0
    for filename in scripts:
        if filename not in applied:
            record_applied(conn, filename)
            print(f"  Marked: {filename}")
            seeded += 1
    if seeded == 0:
        print("Nothing to seed — all migrations already recorded.")
    else:
        print(f"\n✓ Seeded {seeded} migration(s) as applied.")


def cmd_run(conn):
    applied = get_applied(conn)
    scripts = get_all_scripts()
    pending = [s for s in scripts if s not in applied]

    if not pending:
        print("✓ All migrations applied. Nothing to run.")
        return

    print(f"Found {len(pending)} pending migration(s):\n")
    for s in pending:
        print(f"  - {s}")
    print()

    for filename in pending:
        path = os.path.join(MIGRATIONS_DIR, filename)
        print(f"Running {filename} ...", end=" ", flush=True)

        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print("FAILED\n")
            print(result.stderr)
            print(f"Migration '{filename}' failed. Stopping.")
            sys.exit(1)

        record_applied(conn, filename)
        print("done")

    print(f"\n✓ Applied {len(pending)} migration(s) successfully.")


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    conn = get_connection()
    ensure_tracking_table(conn)

    if arg == '--seed':
        cmd_seed(conn)
    elif arg == '--status':
        cmd_status(conn)
    elif arg is None:
        cmd_run(conn)
    else:
        print(f"Unknown argument: {arg}")
        print("Usage: python3 migrate.py [--seed | --status]")
        sys.exit(1)

    conn.close()