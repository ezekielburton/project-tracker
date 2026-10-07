"""The admin Database page's cards: tiles, size over 30 days, the largest
tables, the slowest queries and maintenance."""
from app.modules.dashboard.lib import admin_charts
from app.modules.dashboard.lib.admin_pages.common import bar_rows, split, tile
from app.modules.system.lib import fmt
from app.modules.system.services import database, health

LAYOUT = (('tiles',), ('size', 'tables'), ('queries', 'maintenance'))


def _tiles(snapshot, now):
    t = database.tiles(now)
    size, unit = split(t['size'])
    backup = t['backup']
    if backup:
        backup_sub = ' · '.join(part for part in (backup['size'], backup['result'], backup['ago']) if part)
    return {'tiles': [
        tile('Database size', size, unit, t['growth']),
        tile('Connections', t['connections'], f"/{t['max_connections']}", f"peak today {t['peak_today']}",
             pct=t['connections_pct'], tone=t['connections_state']),
        tile('Cache hit', t['cache_pct'], '%', f"shared_buffers {t['shared_buffers']}",
             pct=t['cache_pct'], tone=t['cache_state']),
        tile('Last backup', backup['time'] if backup else None, None,
             backup_sub if backup else 'No backup yet',
             sub_tone=backup['state'] if backup and backup['state'] != health.GREEN else None),
    ]}


def _size(snapshot, now):
    history = database.size_history(now)
    if len(history) < 2:
        return {'chart': None}
    start = now - database.GROWTH_WINDOW
    chart = admin_charts.lines({'size': history}, start, now, from_zero=False, label=lambda moment, v: (
        f"{fmt.local(moment).day} {fmt.local(moment):%b} · {fmt.size(v['size'])}"))
    return {'chart': chart, 'ticks': admin_charts.date_ticks(start, now, fmt.local),
            'scale': admin_charts.scale(chart['top'], chart['low'], fmt.size),
            'latest': fmt.size(history[-1][1])}


def _tables(snapshot, now):
    return {'rows': bar_rows(database.largest_tables(), 'name', 'bytes', lambda row: row['size'])}


def _queries(snapshot, now):
    return {'queries': database.queries(now)}


def _maintenance(snapshot, now):
    return {'m': database.maintenance(snapshot, now)}


PARTS = {'tiles': _tiles, 'size': _size, 'tables': _tables, 'queries': _queries,
         'maintenance': _maintenance}
