"""
The two charts on My performance, drawn as SVG on the server.

No chart library, for two reasons: OVP has no charting dependency and this
module is not the place to add one, and a canvas chart prints blank. The PDF
export is the whole point of this page, so the chart has to be real markup.

Colours come in as CSS variables, so both themes and the light-only report
each get the right pair without this file knowing which is which.

**Size the viewBox to roughly the width it will render at.** The SVG scales
to fill its container, and everything inside scales with it — including the
type. A 556-wide chart stretched across a 1160px card renders its 9px labels
at 19px. That is why the screen and the report ask for different widths
rather than sharing one and hoping.
"""
import math

# Roughly the width each surface renders a chart at, so the scale factor
# stays near 1 and the labels come out the size they were written. The
# default heights are chosen so the two charts together fill the column
# rather than floating in it — the aspect is the only height control an
# SVG scaled to its container has.
SCREEN_WIDTH = 1100
PRINT_WIDTH = 690

GRID_LINES = 3

# Share of a month's slot the two bars take between them; the rest is the
# gap to the next month.
GROUP_SHARE = 0.62
BAR_GAP = 4

AXIS_FONT = 12
TICK_FONT = 12.5


# Gridline steps, per decade. Denser than a plain 1-2-5 ladder on purpose:
# with three gridlines, a max of 16 on a 1-2-5 ladder reaches for a top of
# 30 and leaves half the chart empty above the bars. 6/12/18 is just as
# sayable and fits.
_STEPS = (1, 2, 3, 4, 5, 6, 8, 10)


def _nice_top(value):
    """A round number at or above the tallest bar, so the gridlines land on
    values a person would actually say out loud — and no higher than it has
    to be, because headroom is chart the reader cannot use."""
    if value <= 0:
        return 4
    raw = value / GRID_LINES
    magnitude = 10 ** math.floor(math.log10(raw))
    for step in _STEPS:
        if step * magnitude >= raw:
            return int(round(step * magnitude * GRID_LINES))
    return int(round(10 * magnitude * GRID_LINES))


def _gridlines(top, floor, span):
    """Evenly-spaced lines with whole-number labels. At a small top (a chart
    maxing at 1 or 2) three evenly-spaced labels round into duplicates like
    0, 1, 1 — so step by whole numbers there and draw one line per unit. Any
    remaining rounding collision is dropped rather than drawn twice."""
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
    """Planned against completed, two bars per month.

    Returns a view model rather than a string: the template draws it, so the
    markup stays readable and the numbers stay testable. Bar widths come off
    the chart width, so six months and twelve months both look deliberate.
    """
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
    """Average days to close, month by month.

    A month with nothing closed is a break in the line, not a zero — nothing
    closed is not instant. That is why the points carry `gap`.
    """
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
            # Every other month, so the axis does not turn into a smear.
            'show_label': index % 2 == 0,
        })

    # One <path> per unbroken run, so a gap is a gap rather than a straight
    # line drawn through months where nothing happened.
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
