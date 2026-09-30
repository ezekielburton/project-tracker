"""
Data migration: on the registers where Reported by held who did the work,
that person moves to Done by. Then every entry with no Reported by gets the
HSE officer's person record (the HSE person named on the most entries).
A doer-register entry with neither person is left alone.
Safe to run twice.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DOER_REGISTERS = ('first_aid', 'general_inspection', 'vehicle_inspection',
                  'forklift_inspection', 'machine_maintenance',
                  'induction_training', 'toolbox_talk')
# "HSE" as a whole word, in a person's name or role (Postgres word bounds).
HSE_WORD = r'\mhse\M'


def hse_person(cur):
    """The HSE person named on the most entries, or None if there is none."""
    cur.execute("""
        SELECT p.id FROM hse_people p
        LEFT JOIN hse_entries e ON p.id IN (e.reported_by_id, e.performed_by_id)
        WHERE p.active AND (p.name ~* %s OR coalesce(p.role, '') ~* %s)
        GROUP BY p.id ORDER BY count(e.id) DESC, p.id LIMIT 1;
    """, (HSE_WORD, HSE_WORD))
    row = cur.fetchone()
    return row[0] if row else None


def run(conn):
    """Moves doers, then fills empty Reported by. Returns a summary dict.
    The caller commits."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE hse_entries SET performed_by_id = reported_by_id, reported_by_id = NULL
        WHERE register = ANY(%s) AND performed_by_id IS NULL AND reported_by_id IS NOT NULL;
    """, (list(DOER_REGISTERS),))
    moved = cur.rowcount

    reporter, filled = hse_person(cur), 0
    if reporter:
        cur.execute("""
            UPDATE hse_entries SET reported_by_id = %s
            WHERE reported_by_id IS NULL
              AND NOT (register = ANY(%s) AND performed_by_id IS NULL);
        """, (reporter, list(DOER_REGISTERS)))
        filled = cur.rowcount
    cur.close()
    return {'moved': moved, 'filled': filled, 'reporter': reporter}


if __name__ == '__main__':
    import psycopg2
    from config import Config

    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    result = run(conn)
    conn.commit()
    conn.close()
    if result['reporter'] is None:
        print("Done — {moved} doer(s) moved to Done by. No HSE person found, so "
              "Reported by was not filled.".format(**result))
    else:
        print("Done — {moved} doer(s) moved to Done by; Reported by filled on "
              "{filled} entr(y/ies).".format(**result))
