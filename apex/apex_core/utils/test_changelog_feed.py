# Copyright (c) 2026, AFMCO and contributors
"""A release is described once: the bell feed reads only the markdown notes that ship with it.

There is no separate hand-written Python list to fall out of sync with those notes — a
duplicate would make thirteen of the shipped tree's thirty-seven releases disagree with the
note the popup shows. Adding a release means adding its file; nothing in Python moves.

The load-bearing test is the synthetic note: it writes a version that exists nowhere in the
source and asserts the feed returns it.
"""

import pathlib
import unittest

import frappe

from apex.apex_core.utils.changelog import get_changelog_feed

NOTES = pathlib.Path(frappe.get_app_path("apex")) / "change_log"
SYNTHETIC = NOTES / "v2" / "v2_9_9.md"


class TestFeedComesFromTheNotes(unittest.TestCase):
    def tearDown(self):
        if SYNTHETIC.exists():
            SYNTHETIC.unlink()

    def test_a_new_note_reaches_the_feed_with_no_python_edit(self):
        """Driven through the feed itself, not the helper, so it fails the same way on a
        build that still keeps a hand-written list: the note is simply not there."""
        SYNTHETIC.write_text(
            "<!-- released: 2026-12-31 09:00:00 -->\n"
            "# Apex 2.9.9\n\nA synthetic release used by the feed test.\n",
            encoding="utf-8",
        )

        titles = [item["title"] for item in get_changelog_feed("2026-12-30 00:00:00")]

        self.assertEqual(titles, ["Apex 2.9.9 — A synthetic release used by the feed test."])

    def test_the_link_defaults_to_the_desk_and_a_note_can_override_it(self):
        SYNTHETIC.write_text(
            "<!-- released: 2026-12-31 09:00:00 -->\n<!-- link: /driver -->\n"
            "# Apex 2.9.9\n\nA synthetic release.\n",
            encoding="utf-8",
        )
        from apex.apex_core.utils.changelog import shipped_releases

        by_title = {item["title"]: item for item in shipped_releases()}
        self.assertEqual(by_title["Apex 2.9.9 — A synthetic release."]["link"], "/driver")
        self.assertTrue(all(item["link"] for item in shipped_releases()))

    def test_a_note_with_no_released_stamp_is_not_a_release(self):
        from apex.apex_core.utils.changelog import shipped_releases

        SYNTHETIC.write_text("# Apex 2.9.9\n\nNo stamp, so not a release.\n", encoding="utf-8")
        self.assertNotIn("2.9.9", " ".join(item["title"] for item in shipped_releases()))

    def test_the_feed_still_filters_by_when_the_reader_last_looked(self):
        SYNTHETIC.write_text(
            "<!-- released: 2026-12-31 09:00:00 -->\n# Apex 2.9.9\n\nA synthetic release.\n",
            encoding="utf-8",
        )
        after = get_changelog_feed("2026-12-30 00:00:00")
        before = get_changelog_feed("2027-01-02 00:00:00")
        self.assertEqual([i["title"] for i in after], ["Apex 2.9.9 — A synthetic release."])
        self.assertEqual(before, [])

    def test_every_shipped_note_carries_its_stamp(self):
        """A note that forgets the stamp vanishes from the feed silently, so the whole
        shipped set is checked rather than trusted."""
        from apex.apex_core.utils.changelog import shipped_releases

        on_disk = sorted(
            path.stem for series in NOTES.glob("v[0-9]*") for path in series.glob("v*_*_*.md")
        )
        in_feed = sorted(
            "v" + item["title"].split()[1].replace(".", "_") for item in shipped_releases()
        )
        self.assertEqual(on_disk, in_feed)


if __name__ == "__main__":
    unittest.main()
