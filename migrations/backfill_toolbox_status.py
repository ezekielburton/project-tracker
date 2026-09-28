"""
Data migration: toolbox talks gain a status (Scheduled, Completed,
Cancelled). Every talk filed before that was held, so a talk with no status
becomes Completed. Safe to run twice.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(conn):
    """Marks every status-less toolbox talk Completed; returns how many.
    The caller commits."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE hse_entries
        SET status = 'Completed'
        WHERE register = 'toolbox_talk' AND status IS NULL;
    """)
    updated = cur.rowcount
    cur.close()
    return updated


if __name__ == '__main__':
    import psycopg2
    from config import Config

    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    updated = run(conn)
    conn.commit()
    conn.close()
    print(f"Done — {updated} toolbox talk(s) marked Completed.")
