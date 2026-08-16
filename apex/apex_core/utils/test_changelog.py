# Copyright (c) 2026, AFMCO and contributors
"""Ordering, title clipping and the feed cap in apex_core.utils.changelog.

This suite asserts against ``shipped_releases()`` (changelog.py:52-69), the single source of
release data: markdown notes on disk, not a hand-written Python table.

test_changelog_feed.py owns the disk-reading half of this subject and drives it with a
synthetic note:
  exclusive lower bound + empty-on-future -> ::test_the_feed_still_filters_by_when_the_reader_last_looked
  items carry title / link                -> ::test_a_new_note_reaches_the_feed_with_no_python_edit
                                             and ::test_the_link_defaults_to_the_desk_and_a_note_can_override_it

What is left is what that file does not assert: newest-first ORDER, the 140-character
title clip at its boundary, and the _FEED_MAX truncation — none of which a shipped table
that happens to fit inside the cap can prove.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apex.apex_core.utils import changelog
from apex.apex_core.utils.changelog import get_changelog_feed


def _note(title, creation, link="/app"):
    return {"title": title, "app_name": "apex", "link": link, "creation": creation}


class TestChangelogFeed(unittest.TestCase):
    # Counts are derived from the notes on disk, never hard-coded: a literal would make
    # every release edit this file, and the version that forgot would look like a feed
    # bug rather than a stale assertion.
    def test_the_feed_is_ordered_newest_first(self):
        shipped = changelog.shipped_releases()
        self.assertTrue(shipped, "no release note was read — the disk scan broke")
        items = get_changelog_feed("2000-01-01 00:00:00")
        self.assertEqual(len(items), min(len(shipped), changelog._FEED_MAX))
        self.assertEqual(items[0]["creation"], max(r["creation"] for r in shipped))
        creations = [i["creation"] for i in items]
        self.assertEqual(creations, sorted(creations, reverse=True))

    def test_long_title_is_clipped_to_140_with_ellipsis(self):
        """Clipping belongs to the code, not to whichever release happens to sit
        inside the cap. This read the LAST feed item and called it the long 2.0.0
        note; once the shipped table outgrew ``_FEED_MAX`` that position held a
        short recent release instead, so the assertion changed subject and reddened
        without the clip ever breaking. Feed one title over the limit and one
        exactly at it, so the boundary itself is proven."""
        limit = changelog._FEED_TITLE_MAX
        table = [
            _note("L" * (limit + 1), "2026-01-02 00:00:00"),
            _note("E" * limit, "2026-01-01 00:00:00"),
        ]

        with patch.object(changelog, "shipped_releases", lambda: table):
            over, exact = get_changelog_feed("2000-01-01 00:00:00")

        self.assertEqual(len(over["title"]), limit)
        self.assertTrue(over["title"].endswith("…"))
        self.assertEqual(exact["title"], table[1]["title"], "A title at the limit is untouched.")
        # The shipped notes must also obey the ceiling, whatever they grow to.
        for item in get_changelog_feed("2000-01-01 00:00:00"):
            self.assertLessEqual(len(item["title"]), limit)

    def test_feed_is_truncated_at_the_declared_cap(self):
        """An upper-bound assertion over the shipped notes proves nothing about the
        cap on its own: for most of this app's life there were fewer notes than
        ``_FEED_MAX`` and they simply fitted. Swap in a synthetic table LONGER than the cap
        (newest first, the same ordering shipped_releases keeps) and prove the tail is
        actually dropped."""
        cap = changelog._FEED_MAX
        overflow = 5
        oversized = [
            _note(f"Apex synthetic release {n}", f"2026-01-{n:02d} 00:00:00")
            for n in range(cap + overflow, 0, -1)
        ]

        with patch.object(changelog, "shipped_releases", lambda: oversized):
            items = get_changelog_feed("2000-01-01 00:00:00")

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
