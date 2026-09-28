"""
Data migration: materials in stock becomes one line per material. Rows for
the same material (trimmed, any case) merge into the earliest, which keeps
its opening stock. Each row's received/issued snapshot becomes movements
dated at that row's date; a later row whose opening disagrees with the
running balance first gets a count at that date. The latest non-empty
category, unit, location and reorder level carry over, attachments move to
the kept line, merged rows are deleted and the snapshot keys dropped.
Safe to run twice.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg2.extras import Json

REGISTER = 'materials_in_stock'
# Carried from the latest row that has them; location is a column.
CARRIED_KEYS = ('material_category', 'unit', 'reorder_level')


def _num(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _balance(opening, moves, upto):
    """Opening plus moves dated on or before `upto`, in date order. Mirrors
    lib/stock.py balance()."""
    total = opening or 0
    for move in sorted(moves, key=lambda m: m['date']):
        if move['date'] > upto:
            continue
        if move['kind'] == 'received':
            total += move['qty']
        elif move['kind'] == 'issued':
            total -= move['qty']
        elif move['kind'] == 'count':
            total = move['qty']
    return total


def run(conn):
    """Merges and converts every stock row; returns a summary dict. The
    caller commits."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ref, entry_date, location_id, data
        FROM hse_entries
        WHERE register = %s
        ORDER BY entry_date, id;
    """, (REGISTER,))
    rows = cur.fetchall()

    groups = {}
    for row in rows:
        name = str((row[4] or {}).get('item') or '').strip().lower()
        # A row with no material name cannot be matched, so it stands alone.
        groups.setdefault(name or ('unnamed', row[0]), []).append(row)

    summary = {'lines': len(groups), 'merged': 0, 'moves': 0, 'counts': 0,
               'attachments': 0}
    for group in groups.values():
        keep_id, _, _, keep_location, keep_data = group[0]
        data = dict(keep_data or {})
        moves = [dict(m) for m in data.get('moves') or []]
        opening = _num(data.get('opening_stock'))
        carried = {}
        location = keep_location

        for index, (row_id, ref, entry_date, location_id, row_data) in enumerate(group):
            row_data = row_data or {}
            day = entry_date.isoformat()
            if index:
                stated = _num(row_data.get('opening_stock'))
                if stated is not None and stated != _balance(opening, moves, day):
                    moves.append({'date': day, 'kind': 'count', 'qty': stated,
                                  'note': f'Opening stock on {ref}', 'by_id': None})
                    summary['counts'] += 1
                moves.extend(dict(m) for m in row_data.get('moves') or [])
            for kind in ('received', 'issued'):
                qty = _num(row_data.get(kind))
                if qty:
                    moves.append({'date': day, 'kind': kind, 'qty': qty,
                                  'note': f'From {ref}', 'by_id': None})
                    summary['moves'] += 1
            for key in CARRIED_KEYS:
                if row_data.get(key) not in (None, ''):
                    carried[key] = row_data[key]
            if location_id is not None:
                location = location_id

        data.update(carried)
        data.pop('received', None)
        data.pop('issued', None)
        if moves:
            data['moves'] = moves

        if data != (keep_data or {}) or location != keep_location:
            cur.execute("UPDATE hse_entries SET data = %s, location_id = %s WHERE id = %s;",
                        (Json(data), location, keep_id))

        for row_id, *_ in group[1:]:
            cur.execute("UPDATE hse_attachments SET entry_id = %s WHERE entry_id = %s;",
                        (keep_id, row_id))
            summary['attachments'] += cur.rowcount
            cur.execute("DELETE FROM hse_entries WHERE id = %s;", (row_id,))
            summary['merged'] += 1

    cur.close()
    return summary


if __name__ == '__main__':
    import psycopg2
    from config import Config

    conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
    result = run(conn)
    conn.commit()
    conn.close()
    print("Done — {lines} stock line(s); {merged} duplicate row(s) merged; "
          "{moves} movement(s) and {counts} count(s) added; "
          "{attachments} attachment(s) moved.".format(**result))
