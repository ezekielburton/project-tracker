"""The admin Errors page's cards: tiles, errors grouped by signature, 500s by route and the raw tail."""
from app.modules.dashboard.lib.admin_pages.common import tile
from app.modules.system.services import errors

LAYOUT = (('tiles',), ('groups',), ('routes', 'tail'))


def _tiles(snapshot, now):
    t = errors.tiles(now)
    share = t['http_500_pct']
    return {'tiles': [
        tile('Errors · 24h', t['errors'], None),
        tile('Warnings · 24h', t['warnings'], None),
        tile('HTTP 500s · 24h', t['http_500'], None, f'{share}% of requests' if share is not None else None,
             sub_tone='red' if t['http_500'] else None),
        tile('NAS / background · 24h', t['failures'], None),
    ]}


def _groups(snapshot, now):
    return {'groups': errors.groups(now)}


def _routes(snapshot, now):
    return {'rows': errors.routes_500(now)}


def _tail(snapshot, now):
    return {'lines': errors.tail(now)}


PARTS = {'tiles': _tiles, 'groups': _groups, 'routes': _routes, 'tail': _tail}
