"""
Data migration: machine serial numbers were typed into the asset tag. For
each machine with no serial, the tag moves to the serial and the tag is
cleared. Placeholder tags such as "N/A" are cleared first, so they never
become a serial. A machine that already has both keeps both.
Safe to run twice.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tags that mean "none", compared trimmed and lower-case.
PLACEHOLDERS = ('n/a', 'na', 'none', '-', '—')


def run(conn):
    """Clears placeholder tags, then moves real ones to the serial. Returns
    a summary dict. The caller commits."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE hse_assets SET ref = NULL
        WHERE kind = 'machine' AND lower(trim(ref)) = ANY(%s);
    """, (list(PLACEHOLDERS),))
    cleared = cur.rowcount

    cur.execute("""
        UPDATE hse_assets SET serial_no = trim(ref), ref = NULL
        WHERE kind = 'machine'
          AND trim(coalesce(ref, '')) <> ''
          AND trim(coalesce(serial_no, '')) = '';
    """)
    moved = cur.rowcount
    cur.close()
    return {'cleared': cleared, 'moved': moved}


if __name__ == '__main__':
    import psycopg2
    from config import Config

    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    result = run(conn)
    conn.commit()
    conn.close()
    print("Done — {moved} machine tag(s) moved to serial no.; "
          "{cleared} placeholder tag(s) cleared.".format(**result))
