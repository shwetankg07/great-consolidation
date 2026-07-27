"""Redraws the charts and refreshes the generated sections of the README.

Prose in the README is written by hand and left alone. Only the regions
between the generated markers are replaced, so the daily commit touches
numbers and never argument.
"""

import re
import sys
from pathlib import Path

from tracker import charts, store

ROOT = Path(__file__).resolve().parent
README = ROOT / "README.md"

# Six packages, chosen to span the range of outcomes rather than to flatter the
# thesis: two that consolidated hard, one that barely moved, one that grew its
# tree, and the two extremes of package size.
HEADLINE = ["next", "webpack", "eslint", "express", "vue", "react"]

MEGABYTE = 1024 * 1024


def series_from(releases, field, transform=lambda value: value):
    """Ordered date/value runs per headline package, skipping empty cells."""
    series = {}
    for name in HEADLINE:
        run = [
            (row["published"], transform(row[field]))
            for row in releases
            if row["package"] == name and row.get(field)
        ]
        run.sort()
        if len(run) >= 2:
            series[name] = run
    return series


def draw(releases):
    trees = series_from(releases, "tree_size")
    sizes = series_from(releases, "unpacked_bytes", lambda value: value / MEGABYTE)

    for theme in ("light", "dark"):
        charts.write(
            f"trees-{theme}",
            charts.line_chart(
                trees,
                "Dependency trees collapsed",
                "Distinct packages installed alongside each release, by publish date",
                "packages",
                theme,
                tick_format=lambda value: f"{value:,.0f}",
            ),
        )
        charts.write(
            f"sizes-{theme}",
            charts.line_chart(
                sizes,
                "The packages themselves exploded",
                "Unpacked size of the package alone, log scale, by publish date",
                "size",
                theme,
                log=True,
                tick_format=lambda value: f"{value:g} MB",
                label_format=lambda value: f"{value:,.1f} MB",
            ),
        )

    return trees, sizes


def summary_table(releases):
    """First and latest measurement per headline package."""
    lines = [
        "| package | first seen | packages installed | package size | files |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for name in HEADLINE:
        rows = sorted(
            (row for row in releases if row["package"] == name and row.get("tree_size")),
            key=lambda row: row["published"],
        )
        if len(rows) < 2:
            continue
        first, last = rows[0], rows[-1]
        lines.append(
            f"| `{name}` | {first['published'][:7]} | "
            f"{first['tree_size']} → **{last['tree_size']}** | "
            f"{first['unpacked_bytes'] / MEGABYTE:.1f} MB → "
            f"**{last['unpacked_bytes'] / MEGABYTE:.1f} MB** | "
            f"{first['file_count']:,} → **{last['file_count']:,}** |"
        )
    return "\n".join(lines)


def headline(releases):
    """The single most dramatic consolidation in the dataset, stated plainly."""
    best = None
    for name in HEADLINE:
        rows = sorted(
            (row for row in releases if row["package"] == name and row.get("tree_size")),
            key=lambda row: row["published"],
        )
        if len(rows) < 2:
            continue
        drop = rows[0]["tree_size"] - rows[-1]["tree_size"]
        if best is None or drop > best[0]:
            best = (drop, name, rows[0], rows[-1])

    if best is None:
        return "Not enough resolved dependency graphs yet."

    _, name, first, last = best
    shrink = (1 - last["tree_size"] / first["tree_size"]) * 100
    growth = last["unpacked_bytes"] / first["unpacked_bytes"]
    return (
        f"Since {first['published'][:7]}, installing `{name}` went from pulling in "
        f"**{first['tree_size']} packages to {last['tree_size']}**, a {shrink:.0f}% drop. "
        f"Over the same period `{name}` itself grew **{growth:.0f}x**, from "
        f"{first['unpacked_bytes'] / MEGABYTE:.1f} MB to "
        f"{last['unpacked_bytes'] / MEGABYTE:.1f} MB across "
        f"{last['file_count']:,} files."
    )


def replace_block(text, marker, body):
    pattern = re.compile(
        rf"<!-- generated:{marker} -->.*?<!-- /generated:{marker} -->",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise SystemExit(f"README is missing the '{marker}' generated block")
    replacement = (
        f"<!-- generated:{marker} -->\n{body}\n<!-- /generated:{marker} -->"
    )
    # A plain string would have backslashes and group references interpreted.
    return pattern.sub(lambda _: replacement, text)


def main():
    releases = store.load_releases()
    if not releases:
        raise SystemExit("No data. Run backfill.py first.")

    draw(releases)

    daily = store.load_daily()
    latest = max((row["date"] for row in daily), default="never")
    resolved = sum(1 for row in releases if row.get("tree_size"))
    packages = len({row["package"] for row in releases})

    text = README.read_text(encoding="utf-8")
    text = replace_block(text, "headline", headline(releases))
    text = replace_block(text, "table", summary_table(releases))
    text = replace_block(
        text,
        "stats",
        f"`{len(releases):,}` releases measured across `{packages}` packages, "
        f"`{resolved:,}` with a resolved dependency graph. "
        f"Last collected `{latest}`.",
    )
    README.write_text(text, encoding="utf-8")

    print(f"charts redrawn, README updated ({len(releases)} releases, last run {latest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
