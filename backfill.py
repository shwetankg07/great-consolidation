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
"""

import sys
from concurrent.futures import ThreadPoolExecutor

from tracker import tracked_packages
from tracker import depsdev, registry, store

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
    history = registry.release_history(name)
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


def main(argv):
    names = argv[1:] or tracked_packages()
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
