"""change_log/README.md must link every version popup — no skipped versions.

The README is a derived mirror of the per-version notes under change_log/v1/. It
drifted badly (stale tail, whole minor series missing) until it was regenerated
from the popups in 1.54.x (T-267). This guard keeps it complete: every
v1_X_Y_Z.md must have a link in the README, so a new release that forgets to add
its line fails the build.
"""

import glob
import os
import re
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CHANGE_LOG = os.path.join(APP_ROOT, "change_log")
ARABIC = re.compile(r"[؀-ۿ]")


class TestChangelogReadmeComplete(unittest.TestCase):
    def _readme(self):
        with open(os.path.join(CHANGE_LOG, "README.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_every_popup_is_linked(self):
        readme = self._readme()
        popups = [os.path.basename(p) for p in glob.glob(os.path.join(CHANGE_LOG, "v1", "v1_*.md"))]
        self.assertTrue(popups, "no version popups found under change_log/v1/")
        missing = [p for p in popups if f"(v1/{p})" not in readme]
        self.assertEqual(
            sorted(missing),
            [],
            "change_log/README.md is missing links for these version popups "
            f"(regenerate the mirror): {sorted(missing)}",
        )

    def test_readme_is_english(self):
        # The README is the GitHub-facing What's-New index; Arabic product glosses
        # belong in the individual popups, not this summary mirror.
        offenders = [ln for ln in self._readme().splitlines() if ARABIC.search(ln)]
        self.assertEqual(offenders, [], f"Arabic in change_log/README.md: {offenders[:5]}")
