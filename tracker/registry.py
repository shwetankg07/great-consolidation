"""Reads package metadata from the public npm registry.

The registry keeps every published version of every package along with the
date it was published and, since npm 5.6, the unpacked size and file count of
the tarball. That makes the full history of a package retrievable in a single
request, which is why this project does not have to wait a year to have a
chart worth looking at.
"""

import urllib.parse

from .http import get_json

REGISTRY = "https://registry.npmjs.org"


def _quote(name):
    """Scoped names (@angular/core) need the slash percent-encoded."""
    return urllib.parse.quote(name, safe="@")


def is_stable(version):
    """True for a release version, false for any prerelease.

    Semver defines the hyphen as the prerelease separator, so this is the
    whole rule. An earlier version of this checked for known channel names
    (canary, rc, beta) and let 719 rows of junk through: React publishes its
    experimental channel as 0.0.0-<commit sha>, and Astro and Rollup do
    something similar. Those builds are published continuously and are not
    releases, so a chart that includes them is measuring the wrong thing.
    """
    return "-" not in version


def release_history(name):
    """Every stable release of a package that reports a size.

    Returns a list of dicts sorted oldest first. Versions published before npm
    recorded sizes are skipped rather than written as zero, so the dataset
    never contains a fabricated measurement.
    """
    document = get_json(f"{REGISTRY}/{_quote(name)}")
    if document is None:
        return []

    published = document.get("time", {})
    history = []

    for version, meta in (document.get("versions") or {}).items():
        if not is_stable(version) or version not in published:
            continue
        dist = meta.get("dist") or {}
        size = dist.get("unpackedSize")
        if not size:
            continue
        history.append(
            {
                "package": name,
                "version": version,
                "published": published[version][:10],
                "unpacked_bytes": size,
                "file_count": dist.get("fileCount") or 0,
                "direct_deps": len(meta.get("dependencies") or {}),
            }
        )

    history.sort(key=lambda row: (row["published"], row["version"]))
    return history


def publish_date(name, version):
    """The date a specific version was published, or None if unknown.

    The /latest endpoint omits timestamps, so this costs a full document
    fetch. It is only called when the collector meets a version it has never
    recorded, which is a handful of times a week.
    """
    document = get_json(f"{REGISTRY}/{_quote(name)}")
    if document is None:
        return None
    stamp = (document.get("time") or {}).get(version)
    return stamp[:10] if stamp else None


def latest_release(name):
    """The current dist-tag latest, or None if it reports no size."""
    meta = get_json(f"{REGISTRY}/{_quote(name)}/latest")
    if meta is None:
        return None

    dist = meta.get("dist") or {}
    if not dist.get("unpackedSize"):
        return None

    return {
        "package": name,
        "version": meta["version"],
        "unpacked_bytes": dist["unpackedSize"],
        "file_count": dist.get("fileCount") or 0,
        "direct_deps": len(meta.get("dependencies") or {}),
    }
