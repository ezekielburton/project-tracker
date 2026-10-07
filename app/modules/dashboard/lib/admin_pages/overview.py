"""The admin Overview's cards: the status strip, Needs attention, today's use and the next jobs."""
from flask import url_for

from app.modules.dashboard.lib import admin_charts
from app.modules.dashboard.lib.admin_pages.common import link, when
from app.modules.system.lib import fmt
from app.modules.system.services import health


def _strip(snapshot, now):
    return {'tiles': health.status_strip(snapshot, now)}


def _attention(snapshot, now):
    items = health.needs_attention(snapshot, now)
    for item in items:
        item['link'] = link(item['page'])
    return {'items': items}


def _today(snapshot, now):
    numbers = health.today(now)
    weeks = numbers['weeks']
    labels = [f"{week['start'].day} {week['start']:%b}" for week in (weeks[0], weeks[len(weeks) // 2], weeks[-1])]
    titles = [f"Week of {week['start'].day} {week['start']:%b} · {week['actions']:,} actions" for week in weeks]
    chart = admin_charts.bars([week['actions'] for week in weeks], titles=titles)
    return dict(numbers, chart=chart, labels=labels, scale=admin_charts.scale(chart['top'], show=fmt.count))


def _jobs(snapshot, now):
    upcoming = health.next_jobs(snapshot)
    for job in upcoming:
        job['when'] = when(job['next'], now)
    return {'jobs': upcoming, 'jobs_url': url_for('projects.admin_jobs')}


PARTS = {'strip': _strip, 'attention': _attention, 'today': _today, 'jobs': _jobs}
