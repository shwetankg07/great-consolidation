"""Resolves transitive dependency graphs via Google's deps.dev API.

deps.dev answers the question this project actually cares about: how many
distinct packages does installing this one drag in? It resolves historical
versions too, which is what makes the eight-year backfill possible.

One caveat worth stating plainly, and it is repeated in the README: this is
deps.dev's resolution, not the output of any particular package manager. A
real lockfile from npm, pnpm or yarn may differ. The number is consistent
across time and across packages, which is what a trend needs, but it is not a
substitute for inspecting your own install.
"""

import urllib.parse

from .http import Unavailable, get_json

API = "https://api.deps.dev/v3"


def _quote(name):
    return urllib.parse.quote(name, safe="")


def tree_size(name, version):
    """Count of distinct packages in the resolved dependency graph.

    Includes the root package itself, so a package with no dependencies at all
    resolves to 1. Returns None when deps.dev has not resolved this version,
    which happens for very new releases and for a handful of older ones.
    """
    url = f"{API}/systems/npm/packages/{_quote(name)}/versions/{_quote(version)}:dependencies"
    try:
        graph = get_json(url)
    except Unavailable:
        # An unreachable dependency service must not cost us the day's
        # registry measurements. The row is written with an empty tree_size
        # and the next release of this package fills the gap.
        return None
    if graph is None:
        return None

    nodes = graph.get("nodes")
    if not nodes:
        return None
    return len(nodes)
