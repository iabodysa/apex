# Copyright (c) 2026, AFMCO and contributors
"""Regression test: the change-log files something in the running app reads.

Two readers, both fed by `apex/change_log/`:

* `frappe.utils.change_log.get_change_log_for_app` (`frappe/utils/change_log.py:60-86`)
  drives the "Updated To A New Version" Desk popup. It walks every entry of
  `change_log/v<major>/`, parses each NAME as a version, and returns the notes
  in `(from_version, to_version]`.
* `apex.apex_core.utils.changelog.shipped_releases` feeds the notification-bell
  Changelog Feed through the `get_changelog_feed` hook (`apex/hooks.py:593`). It
  keeps only notes carrying an `<!-- released: ... -->` marker.

The tests below grade what each reader would actually find for the version this
package declares, not the shape of the folder: a release whose note is missing,
misnamed or unmarked shows a user nothing, and nothing else in the tree fails.
"""

from pathlib import Path
import re
import unittest

from semantic_version import Version

import apex


# The installed package, never a path derived from this file: the suite lives outside the
# app, so `parents[1]` resolves to .claude/tests/apex and every assertion below graded a
# change_log directory that does not exist.
APP_ROOT = Path(apex.__file__).resolve().parent


def _series_head_file():
    """Path to the note for the version this app currently ships.

    A naive anchor might point at ``v<major>_<minor>_0.md``, the head of the minor
    series — but that is not what the popup reads. ``get_change_log_for_app``
    (frappe/utils/change_log.py:60-86) walks the whole major folder and keeps every file
    whose version satisfies ``from_version < version <= to_version`` — a ``.0`` note is one
    candidate among many and is required by nothing. What the guard should protect is that
    the version being SHIPPED has a note, because that is the one every upgrading site is
    guaranteed to be shown. Apex has never shipped a 2.6.0, so the old anchor demanded a
    file that correctly does not exist.
    """
    major = apex.__version__.split(".")[0]
    return APP_ROOT / "change_log" / f"v{major}" / f"v{apex.__version__.replace('.', '_')}.md"


def _series_folder():
    return APP_ROOT / "change_log" / f"v{apex.__version__.split('.')[0]}"


def _shipped_versions():
    """Every note version in the current major-series folder, ascending."""
    found = []
    for entry in _series_folder().iterdir():
        stem = entry.name[:-3] if entry.name.endswith(".md") else entry.name
        found.append(Version(stem[1:].replace("_", ".")))
    return sorted(found)


class TestChangeLogPopup(unittest.TestCase):
    def test_current_series_has_official_change_log_file(self):
        head = _series_head_file()
        self.assertTrue(
            head.exists(),
            f"Missing official Frappe popup changelog file for the current minor series: {head}",
        )

    def test_current_change_log_mentions_user_visible_updates(self):
        """The current series' popup changelog must be a substantive, well-formed
        release note that actually describes user-visible updates.

        Version-agnostic on purpose: it guards that every release ships a real
        changelog (a heading naming the minor series, and bullet points) without
        pinning the test to terminology from any single release.
        """
        major, minor = apex.__version__.split(".")[:2]
        head = _series_head_file()
        content = head.read_text(encoding="utf-8")

        self.assertRegex(
            content,
            re.compile(rf"^#\s+.*{re.escape(f'{major}.{minor}')}", re.MULTILINE),
            f"Changelog {head.name} must open with a heading naming series {major}.{minor}.",
        )

        bullets = re.findall(r"^\s*[-*]\s+\S", content, re.MULTILINE)
        self.assertGreaterEqual(
            len(bullets),
            3,
            f"Changelog {head.name} must list at least three changes; found {len(bullets)}.",
        )

    def test_every_entry_in_the_series_folder_parses_as_a_version(self):
        """One unparseable name in `v<major>/` breaks the popup for every user.

        `get_change_log_for_app` parses the name of EVERY entry it finds in the
        folder before deciding whether it is in range, so a stray README or an
        editor backup raises out of the whole call rather than being skipped.
        """
        folder = _series_folder()
        rejected = []
        for entry in sorted(folder.iterdir()):
            stem = entry.name[:-3] if entry.name.endswith(".md") else entry.name
            try:
                Version(stem[1:].replace("_", "."))
            except ValueError:
                rejected.append(entry.name)
        self.assertEqual(
            rejected,
            [],
            f"{folder} holds entries frappe cannot parse as a version, which raises out of "
            f"the popup for every user: {', '.join(rejected)}",
        )

    def test_popup_has_something_to_show_for_the_current_version(self):
        """The clause the popup actually has to satisfy.

        A user sitting on an older shipped version opens the desk after an
        upgrade. `get_change_log_for_app` returns the notes in
        `(their version, this version]`; if this version shipped no note of its
        own, that list is EMPTY and the popup never appears. The series head
        existing is not enough — 2.8.1 with only `v2_8_0.md` shows nothing.
        """
        from frappe.utils.change_log import get_change_log_for_app

        current = Version(apex.__version__)
        earlier = [version for version in _shipped_versions() if version < current]
        self.assertTrue(
            earlier,
            f"No note ships below {current}, so no upgrade path into it can be graded.",
        )
        previous = earlier[-1]

        found = get_change_log_for_app("apex", from_version=str(previous), to_version=str(current))
        self.assertTrue(
            found,
            f"Frappe's popup finds nothing for a user upgrading {previous} -> {current}. "
            f"Add {_series_folder().name}/v{str(current).replace('.', '_')}.md.",
        )
        self.assertEqual(
            found[0][0],
            str(current),
            f"The newest note the popup would show is {found[0][0]}, not the shipped "
            f"version {current}.",
        )

    def test_bell_feed_carries_the_current_release(self):
        """The second reader: a note with no `released:` marker is dropped silently.

        `shipped_releases` skips any note whose body lacks the marker, so a
        release can ship a popup note and still be invisible in the bell.
        """
        from apex.apex_core.utils.changelog import shipped_releases

        versions = [release["title"] for release in shipped_releases()]
        self.assertTrue(
            any(title.startswith(f"Apex {apex.__version__} ") or title == f"Apex {apex.__version__}"
                for title in versions),
            f"The changelog feed carries no entry for {apex.__version__}; its note is "
            f"missing the `<!-- released: YYYY-MM-DD HH:MM:SS -->` marker.",
        )


if __name__ == "__main__":
    unittest.main()
