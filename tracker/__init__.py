"""Daily metrics for the npm ecosystem."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def tracked_packages():
    """Flat list of every package named in packages.json, order preserved."""
    config = json.loads((ROOT / "packages.json").read_text(encoding="utf-8"))
    names = []
    for group in config["groups"].values():
        names.extend(group)
    return names


def package_groups():
    config = json.loads((ROOT / "packages.json").read_text(encoding="utf-8"))
    return config["groups"]
