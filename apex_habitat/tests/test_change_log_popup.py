"""Regression test: official Frappe change-log popup files.

Frappe shows the "Updated To A New Version" Desk popup from files under
`<app>/change_log/v<major>/vX_Y_Z.md`, not from the Changelog Feed bell.

The popup is consolidated to ONE file per minor series (series head
`v<major>_<minor>_0.md`), matching ERPNext's coarse-milestone shape, so a
freshly-stamped user sees a bounded per-series note instead of a per-patch
replay. This test guards that the current version's series head ships and is a
well-formed release note.
"""

from pathlib import Path
import re
import unittest

import apex_habitat


APP_ROOT = Path(__file__).resolve().parents[1]


def _series_head_file():
    """Path to the current version's minor-series head changelog file."""
    major, minor = apex_habitat.__version__.split(".")[:2]
    return APP_ROOT / "change_log" / f"v{major}" / f"v{major}_{minor}_0.md"


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
        major, minor = apex_habitat.__version__.split(".")[:2]
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


if __name__ == "__main__":
    unittest.main()
