"""The daily run.

Records what every tracked package looks like today, and picks up any release
published since the last run so the historical spine stays complete without a
second backfill.

Written to be safe to run twice in a day: today's rows are replaced, not
appended, and known releases are never rewritten.
"""

import datetime
import sys
from concurrent.futures import ThreadPoolExecutor

from tracker import ROOT, tracked_packages
from tracker import depsdev, registry, store
from tracker.http import Unavailable

WORKERS = 8


def snapshot(name):
    """Today's numbers for one package, or None if it could not be read.

    A failure here is deliberately not fatal. One unreachable package should
    cost one row, not the whole day's collection, because a run that raises
    produces no commit at all.
    """
    try:
        latest = registry.latest_release(name)
    except Unavailable as error:
        print(f"  skipped {name}: {error}")
        return None

    if latest is None:
        return None
    latest["tree_size"] = depsdev.tree_size(name, latest["version"])
    return latest


def main():
    # UTC explicitly, because the workflow runner is on UTC and a local run
    # from another timezone would otherwise write a different date for the
    # same moment. India is UTC+5:30, so a late-night local run would land on
    # tomorrow's row.
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    names = tracked_packages()

    with ThreadPoolExecutor(WORKERS) as pool:
        snapshots = [row for row in pool.map(snapshot, names) if row]

    if len(snapshots) < len(names) * 0.5:
        print(
            f"Only {len(snapshots)} of {len(names)} packages returned data. "
            "Refusing to record a run this incomplete."
        )
        return 1

    daily_rows = [dict(row, date=today) for row in snapshots]
    store.save_daily(store.merge_daily(store.load_daily(), daily_rows))

    # A snapshot is also a release we may not have on file yet. Backfilling it
    # here means the history stays current without ever re-running backfill.py.
    releases = store.load_releases()
    known = {(row["package"], row["version"]) for row in releases}
    unseen = [row for row in snapshots if (row["package"], row["version"]) not in known]

    # Ask when each was actually published rather than assuming it happened
    # today. A version can be new to us without being new to the world: adding
    # a package to packages.json introduces its entire back catalogue at once,
    # and stamping all of it with today's date would invent history.
    fresh = []
    for row in unseen:
        try:
            published = registry.publish_date(row["package"], row["version"])
        except Unavailable:
            published = None
        fresh.append(
            {
                "package": row["package"],
                "version": row["version"],
                "published": published or today,
                "unpacked_bytes": row["unpacked_bytes"],
                "file_count": row["file_count"],
                "direct_deps": row["direct_deps"],
                "tree_size": row["tree_size"],
            }
        )

    if fresh:
        merged, added = store.merge_releases(releases, fresh)
        store.save_releases(merged)
        for row in fresh:
            print(f"  new release: {row['package']} {row['version']}")
        print(f"{added} release rows added")

    resolved = sum(1 for row in snapshots if row["tree_size"])
    print(f"{today}: {len(snapshots)} packages, {resolved} dependency graphs resolved")

    # The workflow reads this for the commit subject, so the history says what
    # each run actually found instead of "update data" seven hundred times.
    detail = f"{len(fresh)} new release{'s' if len(fresh) != 1 else ''}" if fresh else "no releases"
    (ROOT / ".commit-subject").write_text(
        f"{today}: {len(snapshots)} packages, {detail}\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
