"""Renders the dataset to standalone SVG line charts.

Two charts, never combined onto shared axes: dependency tree size and package
size are different measures on wildly different scales, and overlaying them on
a twin y-axis would invite exactly the misreading this project exists to
correct.

Each chart is emitted once per theme. GitHub picks between them with a
<picture> element, which is more reliable than a media query inside an SVG
that is loaded as an image.

Series colours are assigned per package from a fixed order and never cycled,
so a package keeps its colour across both charts and across redraws.
"""

import datetime
import math
from pathlib import Path

CHARTS = Path(__file__).resolve().parent.parent / "charts"

# Fixed categorical order. Validated as a set for colour-vision deficiency
# separation against both surfaces before being written down here.
SERIES_COLORS = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#9085e9"],
}

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "text": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e8e8e5",
        "axis": "#c9c9c4",
    },
    "dark": {
        "surface": "#1a1a19",
        "text": "#ffffff",
        "muted": "#c3c2b7",
        "grid": "#2e2e2c",
        "axis": "#4a4a46",
    },
}

WIDTH, HEIGHT = 900, 380
# TOP leaves room for the title, the subtitle, and the axis unit label beneath
# them without any of the three colliding.
LEFT, RIGHT, TOP, BOTTOM = 62, 152, 62, 40
PLOT_W = WIDTH - LEFT - RIGHT
PLOT_H = HEIGHT - TOP - BOTTOM

FONT = "ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"


def _escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _day_number(iso_date, origin):
    year, month, day = (int(part) for part in iso_date.split("-"))
    return (datetime.date(year, month, day) - origin).days


def _log_floor(values):
    """The power of ten at or below the smallest positive value.

    Anchoring the log axis to a decade means every gridline the tick loop
    draws is inside the plotted range. A hardcoded floor does not: it leaves
    the lowest label sitting on the axis line while describing a value further
    down, so a dip toward the bottom reads as far deeper than it is.
    """
    positive = [value for value in values if value > 0]
    if not positive:
        return 1.0
    return 10 ** math.floor(math.log10(min(positive)))


class _Scale:
    """Maps dates to x and values to y, linearly or on a log axis."""

    def __init__(self, origin, span_days, top_value, log=False, floor=0.05):
        self.origin = origin
        self.span_days = max(span_days, 1)
        self.top = top_value
        self.log = log
        self.floor = floor

    def x(self, iso_date):
        return LEFT + _day_number(iso_date, self.origin) / self.span_days * PLOT_W

    def y(self, value):
        if self.log:
            value = max(value, self.floor)
            low, high = math.log10(self.floor), math.log10(self.top)
            return TOP + PLOT_H - (math.log10(value) - low) / (high - low) * PLOT_H
        return TOP + PLOT_H - (value / self.top) * PLOT_H


def _nice_ticks(top):
    """A handful of round gridlines that reach but do not exceed the top."""
    if top <= 0:
        return [0]
    step = 10 ** math.floor(math.log10(top / 4)) if top > 4 else 1
    for multiple in (1, 2, 2.5, 5, 10):
        if top / (step * multiple) <= 6:
            step *= multiple
            break
    ticks, value = [], 0
    while value <= top:
        ticks.append(value)
        value += step
    return ticks


def _layout_labels(labels, top, bottom, gap=15):
    """Space end labels apart without letting them leave the canvas.

    Series that finish close together (most of them, once the trees collapse)
    would otherwise stack on top of each other. Pushing them apart in one
    direction alone walks the last few off the bottom edge, so the overflow is
    pushed back up and the gaps re-settled.
    """
    labels.sort(key=lambda item: item[0])
    positions = [min(max(item[0], top), bottom) for item in labels]

    for index in range(1, len(positions)):
        positions[index] = max(positions[index], positions[index - 1] + gap)

    overflow = positions[-1] - bottom
    if overflow > 0:
        positions = [position - overflow for position in positions]
        for index in range(len(positions) - 2, -1, -1):
            positions[index] = min(positions[index], positions[index + 1] - gap)
        positions = [max(position, top) for position in positions]

    return [(positions[i],) + labels[i][1:] for i in range(len(labels))]


def line_chart(
    series,
    title,
    subtitle,
    y_label,
    theme,
    log=False,
    tick_format=str,
    label_format=None,
    color_index=None,
):
    """Render one chart.

    series is an ordered mapping of package name to a list of
    (iso_date, value) points, already sorted by date.

    Axis ticks and end labels are formatted separately: a log axis wants bare
    powers of ten, while the value beside a series name wants a fixed number
    of decimals.
    """
    label_format = label_format or tick_format
    if color_index is None:
        order = list(series)
        color_index = order.index
    palette = THEMES[theme]
    colors = SERIES_COLORS[theme]

    points = [point for run in series.values() for point in run]
    if not points:
        raise ValueError("no data to chart")

    earliest = min(date for date, _ in points)
    origin = datetime.date(*(int(part) for part in earliest.split("-")))
    span = max(_day_number(date, origin) for date, _ in points)
    peak = max(value for _, value in points)

    # Headroom so the highest marker is not bisected by the top edge. The log
    # axis needs less because a multiplier there is a fraction of a decade,
    # and its gridlines stay valid since they are powers of ten below the top.
    scale = _Scale(
        origin,
        span,
        peak * (1.12 if log else 1.08),
        log=log,
        floor=_log_floor(value for _, value in points),
    )

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" font-family="{FONT}" '
        f'role="img" aria-label="{_escape(title)}. {_escape(subtitle)}">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{palette["surface"]}"/>',
        f'<text x="{LEFT}" y="22" font-size="15" font-weight="600" '
        f'fill="{palette["text"]}">{_escape(title)}</text>',
        f'<text x="{LEFT}" y="39" font-size="11.5" '
        f'fill="{palette["muted"]}">{_escape(subtitle)}</text>',
    ]

    if log:
        decade = math.floor(math.log10(scale.floor))
        ticks = []
        while 10**decade <= scale.top:
            ticks.append(10**decade)
            decade += 1
    else:
        ticks = _nice_ticks(scale.top)

    for value in ticks:
        y = scale.y(value)
        if not TOP - 1 <= y <= TOP + PLOT_H + 1:
            continue
        out.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" x2="{LEFT + PLOT_W}" y2="{y:.1f}" '
            f'stroke="{palette["grid"]}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{LEFT - 9}" y="{y + 4:.1f}" font-size="10.5" text-anchor="end" '
            f'fill="{palette["muted"]}">{_escape(tick_format(value))}</text>'
        )

    out.append(
        f'<text x="{LEFT - 9}" y="{TOP - 10}" font-size="10.5" text-anchor="end" '
        f'fill="{palette["muted"]}">{_escape(y_label)}</text>'
    )

    first_year = origin.year + 1
    last_year = origin.year + span // 365
    for year in range(first_year, last_year + 1):
        if (year - first_year) % 2:
            continue
        x = scale.x(f"{year}-01-01")
        out.append(
            f'<text x="{x:.1f}" y="{TOP + PLOT_H + 20}" font-size="10.5" '
            f'text-anchor="middle" fill="{palette["muted"]}">{year}</text>'
        )

    out.append(
        f'<line x1="{LEFT}" y1="{TOP + PLOT_H}" x2="{LEFT + PLOT_W}" y2="{TOP + PLOT_H}" '
        f'stroke="{palette["axis"]}" stroke-width="1"/>'
    )

    endpoints = []
    for name, run in series.items():
        if len(run) < 2:
            continue
        # Keyed on the package, never on its position in this particular
        # chart. Indexing by enumeration means that if one series is missing
        # from one of the two charts, every series after it shifts a colour
        # and the same package appears in two colours across the pair.
        color = colors[color_index(name) % len(colors)]
        path = " ".join(
            ("M" if step == 0 else "L") + f"{scale.x(date):.1f} {scale.y(value):.1f}"
            for step, (date, value) in enumerate(run)
        )
        out.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        final_date, final_value = run[-1]
        endpoints.append(
            (scale.y(final_value), name, color, scale.x(final_date), final_value)
        )

    # Direct labels are not decoration here. Several palette slots sit below a
    # 3:1 contrast ratio against the light surface, so identity has to be
    # carried by something other than colour alone.
    for y, name, color, x, value in _layout_labels(endpoints, TOP + 4, TOP + PLOT_H):
        out.append(
            f'<circle cx="{x:.1f}" cy="{scale.y(value):.1f}" r="4" fill="{color}" '
            f'stroke="{palette["surface"]}" stroke-width="2"/>'
        )
        # A leader line keeps a nudged label attached to the point it names.
        if abs(y - scale.y(value)) > 3:
            out.append(
                f'<path d="M{x + 5:.1f} {scale.y(value):.1f} '
                f'L{LEFT + PLOT_W + 8:.1f} {y:.1f}" fill="none" '
                f'stroke="{color}" stroke-width="1" opacity="0.45"/>'
            )
        out.append(
            f'<text x="{LEFT + PLOT_W + 14}" y="{y + 4:.1f}" font-size="11.5">'
            f'<tspan fill="{palette["text"]}" font-weight="600">{_escape(name)}</tspan>'
            f'<tspan dx="5" fill="{palette["muted"]}">{_escape(label_format(value))}</tspan>'
            f"</text>"
        )

    out.append("</svg>")
    return "\n".join(out)


def write(name, svg):
    CHARTS.mkdir(parents=True, exist_ok=True)
    (CHARTS / f"{name}.svg").write_text(svg, encoding="utf-8")
