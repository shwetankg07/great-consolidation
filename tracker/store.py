"""Reading and writing the two CSV datasets.

Both files are kept sorted and are rewritten in full on every save. That costs
nothing at this size and buys a property worth having: the daily commit diff
shows exactly what changed, instead of an append that reorders on a whim.

  releases.csv  one row per (package, version). The historical spine. Rows are
                immutable once written; a published version's size never
                changes.
  daily.csv     one row per (date, package). What the latest version was on a
                given day. This is what advances even on days when nothing in
                the ecosystem is released.
"""

import csv
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

RELEASE_FIELDS = [
    "package",
    "version",
    "published",
    "unpacked_bytes",
    "file_count",
    "direct_deps",
    "tree_size",
]

DAILY_FIELDS = [
    "date",
    "package",
    "version",
    "unpacked_bytes",
    "file_count",
    "direct_deps",
    "tree_size",
]

INTEGER_FIELDS = {"unpacked_bytes", "file_count", "direct_deps", "tree_size"}


def _read(path, fields):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for field in fields:
            if field in INTEGER_FIELDS:
                row[field] = int(row[field]) if row.get(field) else None
    return rows


def _write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def load_releases():
    return _read(DATA / "releases.csv", RELEASE_FIELDS)


def save_releases(rows):
    rows = sorted(rows, key=lambda row: (row["package"], row["published"], row["version"]))
    _write(DATA / "releases.csv", RELEASE_FIELDS, rows)


def load_daily():
    return _read(DATA / "daily.csv", DAILY_FIELDS)


def save_daily(rows):
    rows = sorted(rows, key=lambda row: (row["date"], row["package"]))
    _write(DATA / "daily.csv", DAILY_FIELDS, rows)


def merge_releases(existing, incoming):
    """Add releases we have not seen before, leaving known rows untouched.

    Keyed on (package, version). A version that already exists is never
    rewritten, so a backfill re-run cannot silently rewrite history.
    """
    index = {(row["package"], row["version"]): row for row in existing}
    added = 0
    for row in incoming:
        key = (row["package"], row["version"])
        if key not in index:
            index[key] = row
            added += 1
    return list(index.values()), added


def merge_daily(existing, incoming):
    """Upsert today's rows, keyed on (date, package).

    Re-running the collector on the same day corrects that day's row rather
    than duplicating it, which matters when a run is retried after a failure.
    """
    index = {(row["date"], row["package"]): row for row in existing}
    for row in incoming:
        index[(row["date"], row["package"])] = row
    return list(index.values())
