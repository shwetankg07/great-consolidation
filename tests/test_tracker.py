"""Tests for the pure logic: version filtering, merging, sampling, layout.

Nothing here touches the network. The upstream clients are thin wrappers over
one HTTP call each, and mocking them would test the mock.
"""

import datetime
import math
import unittest

from backfill import quarterly_sample
from tracker import charts, registry, store


class VersionFiltering(unittest.TestCase):
    def test_plain_versions_are_stable(self):
        for version in ("1.0.0", "16.2.12", "0.0.1"):
            self.assertTrue(registry.is_stable(version), version)

    def test_prereleases_are_rejected(self):
        for version in ("15.0.0-canary.3", "5.0.0-rc.1", "1.0.0-beta", "2.0.0-alpha.7"):
            self.assertFalse(registry.is_stable(version), version)

    def test_hyphen_alone_does_not_disqualify(self):
        # Rare, but a build suffix is not a prerelease channel.
        self.assertTrue(registry.is_stable("1.2.3-patched"))

    def test_scoped_names_keep_their_at_sign(self):
        self.assertEqual(registry._quote("@angular/core"), "@angular%2Fcore")


class ReleaseMerging(unittest.TestCase):
    def setUp(self):
        self.existing = [
            {"package": "next", "version": "1.0.0", "published": "2020-01-01",
             "unpacked_bytes": 100, "file_count": 5, "direct_deps": 2, "tree_size": 9},
        ]

    def test_new_versions_are_added(self):
        incoming = [
            {"package": "next", "version": "2.0.0", "published": "2021-01-01",
             "unpacked_bytes": 200, "file_count": 9, "direct_deps": 1, "tree_size": 4},
        ]
        merged, added = store.merge_releases(self.existing, incoming)
        self.assertEqual(added, 1)
        self.assertEqual(len(merged), 2)

    def test_known_versions_are_never_rewritten(self):
        # A published version's size is fixed. If upstream ever reports
        # something different, the original measurement wins.
        incoming = [dict(self.existing[0], unpacked_bytes=999999)]
        merged, added = store.merge_releases(self.existing, incoming)
        self.assertEqual(added, 0)
        self.assertEqual(merged[0]["unpacked_bytes"], 100)


class DailyMerging(unittest.TestCase):
    def test_rerunning_the_same_day_replaces_rather_than_duplicates(self):
        existing = [{"date": "2026-07-28", "package": "next", "version": "16.0.0"}]
        incoming = [{"date": "2026-07-28", "package": "next", "version": "16.0.1"}]
        merged = store.merge_daily(existing, incoming)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["version"], "16.0.1")

    def test_a_new_day_is_appended(self):
        existing = [{"date": "2026-07-28", "package": "next", "version": "16.0.0"}]
        incoming = [{"date": "2026-07-29", "package": "next", "version": "16.0.0"}]
        self.assertEqual(len(store.merge_daily(existing, incoming)), 2)


class QuarterlySampling(unittest.TestCase):
    def _history(self, dates):
        return [{"published": date, "version": str(i)} for i, date in enumerate(dates)]

    def test_one_release_per_quarter(self):
        history = self._history(
            ["2020-01-05", "2020-02-10", "2020-03-30", "2020-04-01", "2020-07-02"]
        )
        picked = quarterly_sample(history)
        self.assertEqual([row["published"] for row in picked],
                         ["2020-01-05", "2020-04-01", "2020-07-02"])

    def test_the_most_recent_release_is_always_included(self):
        # Otherwise the line would stop at the start of the current quarter and
        # the README would quote a stale "latest" figure.
        history = self._history(["2020-01-05", "2020-02-10", "2020-03-30"])
        picked = quarterly_sample(history)
        self.assertEqual(picked[-1]["published"], "2020-03-30")

    def test_empty_history_is_handled(self):
        self.assertEqual(quarterly_sample([]), [])


class LabelLayout(unittest.TestCase):
    def _positions(self, ys, top=0, bottom=300, gap=15):
        labels = [(y, f"s{i}", "#000", 0, y) for i, y in enumerate(ys)]
        return [round(item[0], 3) for item in
                charts._layout_labels(labels, top, bottom, gap)]

    def test_separated_labels_are_left_alone(self):
        self.assertEqual(self._positions([10, 100, 200]), [10, 100, 200])

    def test_colliding_labels_are_pushed_apart(self):
        placed = self._positions([100, 102, 104])
        for earlier, later in zip(placed, placed[1:]):
            self.assertGreaterEqual(later - earlier, 15)

    def test_labels_never_leave_the_canvas(self):
        # Six series finishing within a few pixels of the floor is the normal
        # case for this dataset, not an edge case.
        placed = self._positions([295, 296, 297, 298, 299, 300], bottom=300)
        self.assertLessEqual(max(placed), 300)
        self.assertGreaterEqual(min(placed), 0)

    def test_order_is_preserved_when_crowded(self):
        placed = self._positions([290, 292, 294, 296, 298])
        self.assertEqual(placed, sorted(placed))


class Scaling(unittest.TestCase):
    def test_log_scale_puts_larger_values_higher(self):
        scale = charts._Scale(datetime.date(2020, 1, 1), 365, 100, log=True)
        self.assertLess(scale.y(100), scale.y(1))

    def test_log_scale_floors_zero_instead_of_diverging(self):
        scale = charts._Scale(datetime.date(2020, 1, 1), 365, 100, log=True)
        self.assertTrue(math.isfinite(scale.y(0)))

    def test_ticks_stay_within_the_axis(self):
        for top in (7, 55, 430, 910, 12000):
            ticks = charts._nice_ticks(top)
            self.assertLessEqual(max(ticks), top)
            self.assertLessEqual(len(ticks), 8)
            self.assertEqual(ticks[0], 0)


if __name__ == "__main__":
    unittest.main()
