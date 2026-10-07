"""The admin Performance page's cards: tiles, response time over 24 hours,
page load by module, the slowest routes and the workers."""

from app.modules.dashboard.lib import admin_charts
from app.modules.dashboard.lib.admin_pages.common import bar_rows, split, tile
from app.modules.system.lib import fmt
from app.modules.system.services import performance

LAYOUT = (('tiles',), ('response', 'modules'), ('routes', 'workers'))


def _tiles(snapshot, now):
    s = performance.summary(snapshot, now)
    avg, avg_unit = split(fmt.ms(s['avg_ms']))
    p95, p95_unit = split(fmt.ms(s['p95_ms']))
    errors = s['error_pct']
    return {'tiles': [
        tile('Avg response', avg, avg_unit, f"last 24h · {s['requests']:,} requests"),
        tile('p95 response', p95, p95_unit, f'target under {performance.P95_TARGET_MS} ms',
             pct=s['p95_pct'], tone=s['p95_state']),
        tile('Error rate', errors, '%', f"{s['errors']:,} of {s['requests']:,}" if s['requests'] else None,
             pct=None if errors is None else min(round(100 * errors / performance.ERROR_BAD_PCT), 100),
             tone=s['error_state']),
        tile('SSE connections', s['sse_open'], None, f"{s['workers']} workers" if s['workers'] else None),
    ]}


def _response(snapshot, now):
    series = performance.response_series(now)
    if not series['avg']:
        return {'chart': None}
    start = now - performance.WINDOW
    chart = admin_charts.lines(series, start, now, label=lambda moment, v: (
        f"{fmt.clock(moment)} · avg {fmt.ms(v.get('avg'))} · p95 {fmt.ms(v.get('p95'))}"))
    return {'chart': chart, 'ticks': admin_charts.time_ticks(start, now, fmt.local),
            'scale': admin_charts.scale(chart['top'], show=fmt.ms)}


def _modules(snapshot, now):
    rows = performance.page_load_by_module(now)
    return {'rows': bar_rows(rows, 'module', 'median_ms', lambda row: fmt.ms(row['median_ms']))}


def _routes(snapshot, now):
    rows = performance.slowest_routes(now)
    for row in rows:
        row['avg'], row['p95'] = fmt.ms(row['avg_ms']), fmt.ms(row['p95_ms'])
    return {'rows': rows}


def _workers(snapshot, now):
    return {'w': performance.workers(snapshot, now)}


PARTS = {'tiles': _tiles, 'response': _response, 'modules': _modules, 'routes': _routes,
         'workers': _workers}
