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
        version = apex_habitat.__version__
        major = version.split(".", 1)[0]
        change_log_file = APP_ROOT / "change_log" / f"v{major}" / f"v{version.replace('.', '_')}.md"
        content = change_log_file.read_text(encoding="utf-8")

        required_terms = [
            "Workspace",
            "Room generator",
            "maintenance",
            "security",
            "performance",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertRegex(content, re.compile(re.escape(term), re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
