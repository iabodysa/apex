# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for apex_core.utils.changelog.get_changelog_feed.

Filter + title-clip logic over the static ``_RELEASES`` table.
``frappe.utils.get_datetime`` is a pure date parser (no DB / live site), so a
plain unittest TestCase exercises the feed directly.
"""

from __future__ import annotations

import unittest

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

    def test_feed_is_capped_and_items_carry_expected_keys(self):
        items = get_changelog_feed("2000-01-01 00:00:00")
        self.assertLessEqual(len(items), 20)
        for key in ("title", "app_name", "link", "creation"):
            self.assertIn(key, items[0])


if __name__ == "__main__":
    unittest.main()
