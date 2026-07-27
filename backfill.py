"""One-time historical backfill.

The registry hands back a package's entire published history in one request,
so every release with a recorded size is cheap to collect. Resolving a
dependency graph, by contrast, is one request per version, so those are
sampled rather than exhaustive: one release per package per quarter. That is
ample for a trend line spanning years and keeps the backfill to a few hundred
requests instead of tens of thousands.

Rows whose tree size was not sampled keep an empty tree_size. Nothing is
guessed or interpolated.

    python backfill.py                 all tracked packages
    python backfill.py next webpack    just these
    python backfill.py --repair        fill gaps left by past failures

Repair exists because a release row is never rewritten once stored, which
keeps history immutable but means a version sampled during a deps.dev outage
keeps its empty tree_size forever. Repair is the one operation allowed to fill
those cells in, and only where they are empty.
"""

import sys
from concurrent.futures import ThreadPoolExecutor

from tracker import tracked_packages
from tracker import depsdev, registry, store
from tracker.http import Unavailable

WORKERS = 8


def quarterly_sample(history):
    """First release of each calendar quarter, plus the most recent one."""
    picked, seen = [], set()
    for row in history:
        year, month = row["published"][:4], int(row["published"][5:7])
        quarter = f"{year}Q{(month - 1) // 3 + 1}"
        if quarter not in seen:
            seen.add(quarter)
            picked.append(row)
    if history and picked and picked[-1] is not history[-1]:
        picked.append(history[-1])
    return picked


def collect_package(name):
    try:
        history = registry.release_history(name)
    except Unavailable as error:
        print(f"  {name}: unavailable, skipped ({error})")
        return []
    if not history:
        print(f"  {name}: no sized releases found")
        return []

    sample = quarterly_sample(history)
    resolved = 0
    for row in sample:
        size = depsdev.tree_size(name, row["version"])
        if size:
            row["tree_size"] = size
            resolved += 1

    print(
        f"  {name}: {len(history)} releases, "
        f"{resolved}/{len(sample)} sampled graphs resolved"
    )
    return history


def repair(names):
    """Resolve dependency graphs for sampled versions that are still missing.

    Only ever writes into an empty cell. A tree size already on file stays as
    it was measured, even if deps.dev would answer differently today.
    """
    releases = store.load_releases()
    by_package = {}
    for row in releases:
        by_package.setdefault(row["package"], []).append(row)

    gaps = []
    for name in names:
        history = sorted(by_package.get(name, []), key=lambda row: row["published"])
        for row in quarterly_sample(history):
            if not row.get("tree_size"):
                gaps.append(row)

    if not gaps:
        print("No gaps to repair.")
        return 0

    print(f"Repairing {len(gaps)} sampled versions with no dependency graph")

    def resolve(row):
        row["tree_size"] = depsdev.tree_size(row["package"], row["version"])
        return row

    with ThreadPoolExecutor(WORKERS) as pool:
        repaired = sum(1 for row in pool.map(resolve, gaps) if row["tree_size"])

    store.save_releases(releases)
    print(f"Filled {repaired} of {len(gaps)}; {len(gaps) - repaired} still unresolved upstream")
    return 0


def main(argv):
    arguments = argv[1:]
    if "--repair" in arguments:
        rest = [item for item in arguments if item != "--repair"]
        return repair(rest or tracked_packages())

    names = arguments or tracked_packages()
    print(f"Backfilling {len(names)} packages")

    collected = []
    with ThreadPoolExecutor(WORKERS) as pool:
        for history in pool.map(collect_package, names):
            collected.extend(history)

    existing = store.load_releases()
    merged, added = store.merge_releases(existing, collected)
    store.save_releases(merged)

    with_graphs = sum(1 for row in merged if row.get("tree_size"))
    print(
        f"\nreleases.csv: {len(merged)} rows "
        f"({added} new), {with_graphs} with a resolved dependency graph"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
