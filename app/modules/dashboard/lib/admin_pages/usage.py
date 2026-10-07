"""The admin Usage page's cards: tiles, actions per day, by module, by hour,
recent logins and the emulation log."""
from app.modules.dashboard.lib import admin_charts
from app.modules.dashboard.lib.admin_pages.common import bar_rows, tile
from app.modules.system.lib import fmt
from app.modules.system.services import usage

LAYOUT = (('tiles',), ('daily', 'modules'), ('hours', 'logins', 'emulation'))
# The hour chart always spans at least the working day, wider when there was activity outside it.
WORKDAY = (9, 18)


def _tiles(snapshot, now):
    t = usage.tiles(now)
    top = t['top_module']
    return {'tiles': [
        tile('Active now', t['active_now'], None, f"of {t['staff']} staff"),
        tile('Actions today', t['actions_today'], None, f"avg {t['daily_average']} / day"),
        tile('People this week', t['people_week'], None, f"last week {t['people_last_week']}"),
        tile('Top module', top['module'] if top else None, None,
             f"{top['share']}% of actions · 30 days" if top else 'No actions yet', text=True),
    ]}


def _spread(labels):
    """Four labels evenly picked from a list, first and last included."""
    last = len(labels) - 1
    return [labels[round(last * step / 3)] for step in range(4)] if last >= 3 else labels


def _daily(snapshot, now):
    days = usage.per_day(now)
    chart = admin_charts.bars([day['actions'] for day in days],
                              titles=[f"{day['day']:%a} {day['day'].day} {day['day']:%b} · {day['actions']:,} actions"
                                      for day in days])
    return {'chart': chart, 'scale': admin_charts.scale(chart['top'], show=fmt.count),
            'labels': _spread([f"{day['day']:%a} {day['day'].day}" for day in days]),
            'total': sum(day['actions'] for day in days)}


def _modules(snapshot, now):
    rows = usage.by_module(now)
    return {'rows': bar_rows(rows, 'module', 'actions', lambda row: f"{row['actions']:,}")}


def _hours(snapshot, now):
    counts = usage.by_hour(now)
    active = [hour for hour, count in enumerate(counts) if count]
    first, last = min(active + [WORKDAY[0]]), max(active + [WORKDAY[1]])
    hours = range(first, last + 1)
    chart = admin_charts.bars([counts[hour] for hour in hours],
                              titles=[f'{hour:02d}:00 · {counts[hour]:,} actions' for hour in hours])
    return {'chart': chart, 'scale': admin_charts.scale(chart['top'], show=fmt.count),
            'labels': _spread([f'{hour:02d}' for hour in hours]),
            'total': sum(counts)}


def _logins(snapshot, now):
    return {'logins': usage.recent_logins(now)}


def _emulation(snapshot, now):
    return {'sessions': usage.emulation_log(now)}


PARTS = {'tiles': _tiles, 'daily': _daily, 'modules': _modules, 'hours': _hours,
         'logins': _logins, 'emulation': _emulation}
