"""Reads package metadata from the public npm registry.

The registry keeps every published version of every package along with the
date it was published and, since npm 5.6, the unpacked size and file count of
the tarball. That makes the full history of a package retrievable in a single
request, which is why this project does not have to wait a year to have a
chart worth looking at.
"""

import re
import urllib.parse

from .http import get_json

REGISTRY = "https://registry.npmjs.org"

# Anything with a hyphenated suffix is a prerelease (1.2.3-canary.4). Tracking
# them would swamp the stable line with noise from projects that publish
# nightlies, so they are dropped everywhere.
PRERELEASE = re.compile(r"-(?:canary|rc|beta|alpha|next|exp|dev|insiders|nightly|pre)")


def _quote(name):
    """Scoped names (@angular/core) need the slash percent-encoded."""
    return urllib.parse.quote(name, safe="@")


def is_stable(version):
    return "-" not in version or not PRERELEASE.search(version)


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
