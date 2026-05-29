"""Regression test: official Frappe change-log popup files.

Frappe shows the "Updated To A New Version" Desk popup from files under
`<app>/change_log/v<major>/vX_Y_Z.md`, not from the Changelog Feed bell.
"""

from pathlib import Path
import re
import unittest

import apex_habitat


APP_ROOT = Path(__file__).resolve().parents[1]


class TestChangeLogPopup(unittest.TestCase):
    def test_current_version_has_official_change_log_file(self):
        version = apex_habitat.__version__
        major = version.split(".", 1)[0]
        change_log_file = APP_ROOT / "change_log" / f"v{major}" / f"v{version.replace('.', '_')}.md"

        self.assertTrue(
            change_log_file.exists(),
            f"Missing official Frappe popup changelog file: {change_log_file}",
        )

    def test_current_change_log_mentions_user_visible_updates(self):
        """The current version's popup changelog must be a substantive, well-formed
        release note that actually describes user-visible updates.

        This is version-agnostic on purpose: it guards that every release ships a
        real changelog (a version heading, a "what changed" narrative, and bullet
        points), without pinning the test to terminology from any single release.
        """
        version = apex_habitat.__version__
        major = version.split(".", 1)[0]
        change_log_file = APP_ROOT / "change_log" / f"v{major}" / f"v{version.replace('.', '_')}.md"
        content = change_log_file.read_text(encoding="utf-8")

        # A top-level heading that names the version (e.g. "# Apex 1.1.0").
        self.assertRegex(
            content,
            re.compile(rf"^#\s+.*{re.escape(version)}", re.MULTILINE),
            f"Changelog {change_log_file.name} must open with a heading naming version {version}.",
        )

        # At least one "What changed ..." section describing user-visible updates.
        self.assertRegex(
            content,
            re.compile(r"^#+\s+What changed", re.IGNORECASE | re.MULTILINE),
            f"Changelog {change_log_file.name} must include a 'What changed' section.",
        )

        # At least three bullet points — a real release note, not a stub.
        bullets = re.findall(r"^\s*[-*]\s+\S", content, re.MULTILINE)
        self.assertGreaterEqual(
            len(bullets),
            3,
            f"Changelog {change_log_file.name} must list at least three changes; found {len(bullets)}.",
        )


if __name__ == "__main__":
    unittest.main()
