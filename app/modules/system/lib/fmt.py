"""Short labels for the admin pages: sizes, durations, ages and Dubai times."""
from datetime import timedelta, timezone

DUBAI = timezone(timedelta(hours=4))
_UNITS = ('B', 'KB', 'MB', 'GB', 'TB')


def size(num_bytes):
    """1536 -> '1.5 KB'; None -> None."""
    if num_bytes is None:
        return None
    value, unit = float(num_bytes), 0
    while value >= 1024 and unit < len(_UNITS) - 1:
        value, unit = value / 1024, unit + 1
    return f'{value:.0f} {_UNITS[unit]}' if value >= 100 or unit == 0 else f'{value:.1f} {_UNITS[unit]}'


def ago(then, now):
    """'just now', '3 min ago', '5 h ago', '9 days ago' for a naive-UTC moment."""
    if then is None:
        return None
    seconds = max((now - then).total_seconds(), 0)
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        return f'{int(seconds // 60)} min ago'
    if seconds < 86400:
        return f'{int(seconds // 3600)} h ago'
    days = int(seconds // 86400)
    return '1 day ago' if days == 1 else f'{days} days ago'


def local(moment):
    """A naive-UTC moment as a Dubai datetime."""
    return moment.replace(tzinfo=timezone.utc).astimezone(DUBAI) if moment else None


def clock(moment):
    """Dubai 'HH:MM' for a naive-UTC moment."""
    return local(moment).strftime('%H:%M') if moment else None


def ms(value):
    """640 -> '640 ms', 1820 -> '1.82 s', 75400 -> '75.4 s', 506000 -> '506 s'; None -> None."""
    if value is None:
        return None
    if value < 1000:
        return f'{value:.0f} ms'
    seconds = value / 1000
    return f'{seconds:.2f} s' if seconds < 10 else f'{seconds:.1f} s' if seconds < 100 else f'{seconds:,.0f} s'


def day_time(moment, now):
    """'today 03:10', 'yesterday 16:40', 'Mon 09:03', '12 Sep 09:03' for a past naive-UTC moment."""
    if moment is None:
        return None
    then, today = local(moment), local(now).date()
    days = (today - then.date()).days
    if days == 0:
        return f'today {then:%H:%M}'
    if days == 1:
        return f'yesterday {then:%H:%M}'
    if days < 7:
        return f'{then:%a %H:%M}'
    return f'{then.day} {then:%b %H:%M}'


def count(value):
    """12345.6 -> '12,346'."""
    return f'{value:,.0f}'
