"""Small server-drawn charts for the admin system pages: a column chart and
time lines, as SVG geometry the templates draw. Colours come from CSS classes."""
from datetime import timedelta


def bars(values, width=620, height=70, gap=4):
    """One column per value, scaled to the largest; a zero still shows a sliver."""
    top = max(values) if values and max(values) > 0 else 1
    step = width / max(len(values), 1)
    columns = []
    for index, value in enumerate(values):
        h = max(round(height * value / top, 1), 1.5)
        columns.append({'x': round(index * step + gap / 2, 1), 'y': round(height - h, 1),
                        'w': round(max(step - gap, 1), 1), 'h': h, 'value': value})
    return {'width': width, 'height': height, 'bars': columns}


def lines(series, start, end, width=620, height=140, pad=6):
    """Each series of (moment, value) as polyline points across start..end,
    all scaled to the largest value; an empty series draws nothing."""
    span = (end - start).total_seconds() or 1
    top = max([value for points in series.values() for _, value in points] or [0]) or 1
    paths = {}
    for name, points in series.items():
        coords = []
        for moment, value in points:
            x = round(width * (moment - start).total_seconds() / span, 1)
            y = round(height - pad - (height - 2 * pad) * value / top, 1)
            coords.append(f'{x},{y}')
        paths[name] = ' '.join(coords)
    return {'width': width, 'height': height, 'paths': paths, 'top': top}


def time_ticks(start, end, local, count=5):
    """Evenly spaced axis labels from start to end; the last one reads 'now'."""
    step = (end - start) / (count - 1)
    ticks = [local(start + step * index).strftime('%H:%M') for index in range(count - 1)]
    return ticks + ['now']
