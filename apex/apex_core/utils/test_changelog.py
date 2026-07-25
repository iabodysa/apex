# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for apex_core.utils.changelog.get_changelog_feed.

Filter + title-clip logic over the static ``_RELEASES`` table.
``frappe.utils.get_datetime`` is a pure date parser (no DB / live site), so a
plain unittest TestCase exercises the feed directly.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apex.apex_core.utils import changelog
from apex.apex_core.utils.changelog import get_changelog_feed


class TestChangelogFeed(unittest.TestCase):
    def test_since_before_all_returns_full_feed_newest_first(self):
        items = get_changelog_feed("2000-01-01 00:00:00")
        self.assertEqual(len(items), 7)
        self.assertEqual(items[0]["creation"], "2026-07-25 05:00:00")
        creations = [i["creation"] for i in items]
        self.assertEqual(creations, sorted(creations, reverse=True))

    def test_since_is_an_exclusive_lower_bound(self):
        items = get_changelog_feed("2026-07-24 00:00:00")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["creation"], "2026-07-25 05:00:00")

    def test_future_since_returns_empty(self):
        self.assertEqual(get_changelog_feed("2030-01-01 00:00:00"), [])

    def test_long_title_is_clipped_to_140_with_ellipsis(self):
        items = get_changelog_feed("2000-01-01 00:00:00")
        oldest = items[-1]  # the Apex 2.0.0 generational note, > 140 chars
        self.assertEqual(len(oldest["title"]), 140)
        self.assertTrue(oldest["title"].endswith("…"))

    def test_items_carry_expected_keys(self):
        items = get_changelog_feed("2000-01-01 00:00:00")
        self.assertTrue(items, "The shipped release table must produce a feed.")
        for key in ("title", "app_name", "link", "creation"):
            self.assertIn(key, items[0])

    def test_feed_is_truncated_at_the_declared_cap(self):
        """The shipped ``_RELEASES`` table is far shorter than ``_FEED_MAX``, so the
        real feed can never reach the cap and an upper-bound assertion over it can
        never fail. Swap in a synthetic table LONGER than the cap (newest first, the
        same ordering the shipped table keeps) and prove the tail is actually dropped
        rather than merely fitting."""
        cap = changelog._FEED_MAX
        overflow = 5
        oversized = [
            {
                "title": f"Apex synthetic release {n}",
                "app_name": "apex",
                "link": "/app",
                "creation": f"2026-01-{n:02d} 00:00:00",
            }
            for n in range(cap + overflow, 0, -1)
        ]

        with patch.object(changelog, "_RELEASES", oversized):
            items = changelog.get_changelog_feed("2000-01-01 00:00:00")

        self.assertEqual(
            len(oversized), cap + overflow, "The fixture must overflow the cap."
        )
        self.assertEqual(len(items), cap, "The feed must be truncated to the cap.")
        # Truncation must keep the head (newest) and drop the tail (oldest).
        titles = [i["title"] for i in items]
        self.assertEqual(titles[0], oversized[0]["title"])
        for dropped in oversized[cap:]:
            self.assertNotIn(
                dropped["title"], titles, "Items past the cap must be dropped."
            )


if __name__ == "__main__":
    unittest.main()
