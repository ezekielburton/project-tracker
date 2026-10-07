"""Small server-drawn charts for the admin system pages: a column chart and
time lines, as SVG geometry the templates draw. Colours come from CSS classes."""
from datetime import timedelta


def scale(top, low=0, show=str):
    """The three value labels down a chart's left edge: top, middle, bottom."""
    return [show(top), show(low + (top - low) / 2), show(low)]


def bars(values, width=620, height=70, gap=4, titles=None):
    """One column per value, scaled to the largest; a zero still shows a sliver.
    `titles` (one per value) are the hover labels; the value alone otherwise."""
    top = max(values) if values and max(values) > 0 else 1
    step = width / max(len(values), 1)
    columns = []
    for index, value in enumerate(values):
        h = max(round(height * value / top, 1), 1.5)
        columns.append({'x': round(index * step + gap / 2, 1), 'y': round(height - h, 1),
                        'w': round(max(step - gap, 1), 1), 'h': h, 'value': value,
                        'title': titles[index] if titles else value})
    return {'width': width, 'height': height, 'bars': columns, 'top': top}


def _hover(series, start, span, width, label):
    """Invisible columns, one per moment, each carrying label(moment, {series: value}) as its title."""
    at = {}
    for name, points in series.items():
        for moment, value in points:
            at.setdefault(moment, {})[name] = value
    moments = sorted(at)
    xs = [width * (moment - start).total_seconds() / span for moment in moments]
    columns = []
    for index, moment in enumerate(moments):
        left = 0 if index == 0 else (xs[index - 1] + xs[index]) / 2
        right = width if index == len(xs) - 1 else (xs[index] + xs[index + 1]) / 2
        columns.append({'x': round(left, 1), 'w': round(max(right - left, 1), 1),
                        'title': label(moment, at[moment])})
    return columns


def lines(series, start, end, width=620, height=140, pad=6, from_zero=True, label=None):
    """Each series of (moment, value) as polyline points across start..end,
    all scaled to the largest value; an empty series draws nothing. With
    from_zero False the lowest value sits at the bottom, so slow growth shows.
    `label(moment, values)` titles the hover column at each moment."""
    span = (end - start).total_seconds() or 1
    values = [value for points in series.values() for _, value in points] or [0]
    top = max(values) or 1
    low = 0 if from_zero else min(values)
    rise = (top - low) or 1
    paths = {}
    for name, points in series.items():
        coords = []
        for moment, value in points:
            x = round(width * (moment - start).total_seconds() / span, 1)
            y = round(height - pad - (height - 2 * pad) * (value - low) / rise, 1)
            coords.append(f'{x},{y}')
        paths[name] = ' '.join(coords)
    return {'width': width, 'height': height, 'paths': paths, 'top': top, 'low': low,
            'hover': _hover(series, start, span, width, label) if label else []}


def time_ticks(start, end, local, count=5):
    """Evenly spaced axis labels from start to end; the last one reads 'now'."""
    step = (end - start) / (count - 1)
    ticks = [local(start + step * index).strftime('%H:%M') for index in range(count - 1)]
    return ticks + ['now']


def date_ticks(start, end, local, count=3):
    """Evenly spaced day labels from start to end, e.g. '7 Sep'."""
    step = (end - start) / (count - 1)
    return [f"{local(start + step * index).day} {local(start + step * index):%b}" for index in range(count)]
