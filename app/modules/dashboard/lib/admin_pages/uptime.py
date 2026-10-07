"""The admin Uptime page's cards: tiles, 30 day-blocks, deploy history and incident notes."""
from flask import url_for

from app.modules.dashboard.lib.admin_pages.common import tile
from app.modules.system.lib import fmt
from app.modules.system.services import health, uptime

LAYOUT = (('tiles',), ('days',), ('deploys', 'incidents'))
GOOD_PCT, FAIR_PCT = 99.9, 99.0


def _tiles(snapshot, now):
    s = uptime.summary(snapshot, now)
    pct, restart, deploy = s['pct'], s['since_restart'], s['deploy']
    if s['ongoing']:
        down_sub, down_tone = 'down now', health.RED
    else:
        down_sub = f"{s['down_minutes']} min down"
        down_tone = None if pct is None or pct >= GOOD_PCT else health.AMBER if pct >= FAIR_PCT else health.RED
    return {'tiles': [
        tile('Uptime · 30 days', pct, '%', down_sub, sub_tone=down_tone),
        tile('Incidents', s['incidents'], None, '30 days', sub_tone='red' if s['incidents'] else None),
        tile('Since last restart', f"{restart['days']}d {restart['hours']:02d}h" if restart else None, None,
             restart['date'] if restart else 'No data'),
        tile('Last deploy', deploy['tag'] if deploy else None, None,
             f"{deploy['ago']} · migrations {deploy['migrations']}" if deploy else 'No deploys yet',
             text=True, sub_tone='red' if deploy and not deploy['ok'] else None),
    ]}


def _days(snapshot, now):
    blocks = uptime.days(now)
    for block in blocks:
        block['label'] = f"{block['day'].day} {block['day']:%b}"
    picks = [blocks[index]['label'] for index in (0, 7, 14, 21, 29)]
    return {'blocks': blocks, 'labels': picks}


def _deploys(snapshot, now):
    return {'rows': uptime.deploys(now)}


def _incidents(snapshot, now):
    return {'incidents': uptime.incidents(), 'today': fmt.local(now).date().isoformat(),
            'add_url': url_for('projects.admin_incident_add')}


PARTS = {'tiles': _tiles, 'days': _days, 'deploys': _deploys, 'incidents': _incidents}
