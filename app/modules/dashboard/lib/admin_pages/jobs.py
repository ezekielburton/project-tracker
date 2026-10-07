"""The admin Jobs page's cards: tiles, one row per timer with Run now, and the orphaned-uploads report."""
from flask import url_for

from app.modules.dashboard.lib.admin_pages.common import split, tile, when
from app.modules.system.lib import fmt
from app.modules.system.services import job_board

HELP = 'dashboard.jobs'
LAYOUT = (('tiles',), ('jobs',), ('orphans',))


def _tiles(snapshot, now):
    t = job_board.tiles(snapshot, now)
    upcoming = t['next']
    size, unit = split(fmt.size(t['reclaimed']))
    return {'tiles': [
        tile('Scheduled jobs', t['scheduled'], None),
        tile('Failed · 7 days', t['failed'], None, ', '.join(t['failed_names']) or 'none',
             sub_tone='red' if t['failed'] else None),
        tile('Next run', when(upcoming['next'], now) if upcoming else None, None,
             upcoming['label'] if upcoming else 'No timers yet', text=True),
        tile('Reclaimed · 30 days', size, unit),
    ]}


def _jobs(snapshot, now):
    rows = job_board.rows(snapshot, now)
    for row in rows:
        due = row['due']
        row['next'] = None if due is None else when(due, now) if due > now else 'overdue'
        row['run_url'] = url_for('projects.admin_job_run_now', job_key=row['key'])
    return {'rows': rows}


def _orphans(snapshot, now):
    return {'report': job_board.orphans(now)}


PARTS = {'tiles': _tiles, 'jobs': _jobs, 'orphans': _orphans}
