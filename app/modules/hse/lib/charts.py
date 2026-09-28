"""
View models for the two My performance charts, drawn as server-side SVG so
they print in the PDF report (canvas prints blank). Colours come from CSS
classes in the templates.

Size the viewBox close to the rendered width: the SVG scales to its
container, text included, so an oversized scale factor inflates the labels.
That is why screen and print pass different widths.
"""
import math

# Approximate rendered width per surface, keeping the scale factor near 1.
# Heights set the aspect ratio, the only height control a scaled SVG has.
SCREEN_WIDTH = 1100
PRINT_WIDTH = 690

GRID_LINES = 3

# Share of a month's slot taken by its two bars; the rest is gap.
GROUP_SHARE = 0.62
BAR_GAP = 4

AXIS_FONT = 12
TICK_FONT = 12.5


# Gridline steps per decade. Denser than 1-2-5 so the top sits close to the
# data (a max of 16 gives 6/12/18, not 10/20/30).
_STEPS = (1, 2, 3, 4, 5, 6, 8, 10)


def _nice_top(value):
    """The smallest round axis top at or above `value`, so gridlines land
    on round numbers."""
    if value <= 0:
        return 4
    raw = value / GRID_LINES
    magnitude = 10 ** math.floor(math.log10(raw))
    for step in _STEPS:
        if step * magnitude >= raw:
            return int(round(step * magnitude * GRID_LINES))
    return int(round(10 * magnitude * GRID_LINES))


def _gridlines(top, floor, span):
    """Evenly spaced gridlines with whole-number labels. A small top gets one
    line per unit, since rounding would duplicate labels; any remaining
    duplicates are dropped."""
    if top <= GRID_LINES:
        values = list(range(1, int(top) + 1))
    else:
        values = [round(top * index / GRID_LINES) for index in range(1, GRID_LINES + 1)]

    out, seen = [], set()
    for value in values:
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        out.append({'value': value, 'y': round(floor - span * value / top, 1)})
    return out


def grouped_bars(series, width=SCREEN_WIDTH, height=270,
                 pad_bottom=34, pad_top=16, pad_left=34):
    """Planned vs completed, two bars per month. Returns a view model the
    template draws; bar widths scale with the number of months."""
    top = _nice_top(max([max(row['planned'], row['done']) for row in series] or [0]))
    floor = height - pad_bottom
    span = floor - pad_top

    count = max(len(series), 1)
    step = (width - pad_left) / count
    group_w = step * GROUP_SHARE
    bar_w = max((group_w - BAR_GAP) / 2, 1)

    bars = []
    for index, row in enumerate(series):
        left = pad_left + index * step + (step - group_w) / 2
        for key, offset in (('planned', 0), ('done', bar_w + BAR_GAP)):
            value = row[key] or 0
            bar_h = round(span * value / top, 1) if top else 0
            bars.append({
                'series': key,
                'x': round(left + offset, 1),
                'y': round(floor - bar_h, 1),
                'h': bar_h,
                'w': round(bar_w, 1),
                'value': value,
            })
        bars[-1]['label'] = row['label']
        bars[-1]['label_x'] = round(left + group_w / 2, 1)

    return {'width': width, 'height': height, 'floor': floor,
            'label_y': height - 12, 'axis_font': AXIS_FONT,
            'tick_font': TICK_FONT,
            'gridlines': _gridlines(top, floor, span), 'bars': bars, 'top': top}


def line(series, width=SCREEN_WIDTH, height=340,
         pad_bottom=34, pad_top=34, pad_left=34):
    """Average days to close, month by month. A month with nothing closed
    has y=None and breaks the line; it is not drawn as zero."""
    values = [row['days'] for row in series if row['days'] is not None]
    top = _nice_top(max(values) if values else 0)
    floor = height - pad_bottom
    span = floor - pad_top

    plot = width - pad_left
    step = plot / (len(series) - 1) if len(series) > 1 else 0

    points = []
    for index, row in enumerate(series):
        days = row['days']
        points.append({
            'label': row['label'],
            'x': round(pad_left + index * step, 1),
            'y': None if days is None else round(floor - span * days / top, 1),
            'days': days,
            # Label every other month to keep the axis legible.
            'show_label': index % 2 == 0,
        })

    # One <path> per unbroken run, so empty months leave a gap.
    paths, run = [], []
    for point in points:
        if point['y'] is None:
            if len(run) > 1:
                paths.append(run)
            run = []
        else:
            run.append(point)
    if len(run) > 1:
        paths.append(run)

    drawn = [p for p in points if p['y'] is not None]
    return {
        'width': width, 'height': height, 'label_y': height - 10,
        'axis_font': AXIS_FONT, 'tick_font': TICK_FONT,
        'gridlines': _gridlines(top, floor, span), 'points': points, 'top': top,
        'dot_r': round(width / 190, 1),
        'paths': [' '.join(f"{'M' if i == 0 else 'L'}{p['x']} {p['y']}"
                           for i, p in enumerate(run)) for run in paths],
        'first': drawn[0] if drawn else None,
        'last': drawn[-1] if len(drawn) > 1 else None,
    }
