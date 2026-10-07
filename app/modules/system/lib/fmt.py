"""Short labels for the admin pages: sizes, ages and Dubai times."""
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
