"""The admin System page's cards: host tiles, storage, network, updates and the application."""
from datetime import timedelta

from app.modules.dashboard.lib import admin_charts
from app.modules.dashboard.lib.admin_pages.common import state
from app.modules.system.lib import fmt
from app.modules.system.services import health

CERT_WARN_DAYS, CERT_BAD_DAYS = 30, 7
TEMP_WARN_C, TEMP_BAD_C = 75, 85


def _tiles(snapshot, now):
    tiles = health.host_tiles(snapshot)
    if tiles and tiles['temp_c'] is not None:
        tiles['temp_state'] = state(tiles['temp_c'], TEMP_WARN_C, TEMP_BAD_C)
    return {'tiles': tiles}


def _storage(snapshot, now):
    return {'rows': health.storage(snapshot)}


def _network(snapshot, now):
    series = health.network(now)
    start = now - timedelta(hours=24)
    if not any(series.values()):
        return {'chart': None}
    chart = admin_charts.lines(series, start, now, label=lambda moment, v: (
        f"{fmt.clock(moment)} · out {fmt.size(v.get('sent', 0))} · in {fmt.size(v.get('recv', 0))}"))
    return {'chart': chart, 'ticks': admin_charts.time_ticks(start, now, fmt.local),
            'scale': admin_charts.scale(chart['top'], show=fmt.size)}


def _updates(snapshot, now):
    updates = health.updates(snapshot, now)
    if updates:
        for cert in updates['certs']:
            cert['state'] = state(cert['days_left'], CERT_WARN_DAYS, CERT_BAD_DAYS, high_is_bad=False)
    return {'updates': updates}


def _application(snapshot, now):
    return {'app': health.application(snapshot, now)}


PARTS = {'tiles': _tiles, 'storage': _storage, 'network': _network,
         'updates': _updates, 'application': _application}
