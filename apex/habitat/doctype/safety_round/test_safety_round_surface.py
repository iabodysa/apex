# Copyright (c) 2026, AFMCO and contributors
"""Safety Inspection Report may not ship as a workspace entry point.

It is superseded by Safety Round and carries ``read_only: 1``, but read-only is not
hidden: while the Safety workspace listed it beside Safety Round in the same Safety
Operations card, every role on that workspace was offered the deprecated record as an
equal alternative to the maker-checker flow.

Frappe-free by design — it reads the shipped JSON, so it runs without a site:

    python3 -m unittest apex.habitat.doctype.safety_round.test_safety_round_surface

It lives in its own module rather than beside the maker-checker tests precisely so that
command is true: test_safety_round.py imports frappe, so a standalone run of it dies on
the import and the coverage guard rightly refuses the claim.
"""

from __future__ import annotations

import glob
import json
import os
import unittest

WORKSPACE_GLOB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "*", "workspace", "*", "*.json"
)
DEPRECATED_DOCTYPE = "Safety Inspection Report"


def workspace_links(pattern=WORKSPACE_GLOB):
    """[(workspace label, kind, target)] for every link and shortcut apex ships."""
    found = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict) or data.get("doctype") != "Workspace":
            continue
        label = data.get("label") or data.get("name")
        for row in data.get("links") or []:
            found.append((label, "link", row.get("link_to")))
        for row in data.get("shortcuts") or []:
            found.append((label, "shortcut", row.get("link_to")))
    return found


class TestNoDeprecatedInspectionReportSurface(unittest.TestCase):
    def setUp(self):
        self.links = workspace_links()

    def test_the_scan_is_non_vacuous(self):
        """"Nothing found" is also what a broken glob reports, so absence only
        means anything once the scan is shown to be reading real links."""
        self.assertGreaterEqual(
            len(self.links), 50, "the workspace JSON scan found almost nothing — glob broke"
        )
        self.assertIn(
            ("Safety", "link", "Safety Round"),
            self.links,
            "the scan does not see the Safety Round link it is supposed to be "
            "guarding the neighbourhood of",
        )
        self.assertIn(
            ("Safety", "shortcut", "Safety Round"),
            self.links,
            "the scan does not read shortcut rows, so a deprecated shortcut "
            "would pass unseen",
        )

    def test_no_workspace_offers_the_deprecated_inspection_report(self):
        offenders = sorted(
            "{0} ({1})".format(label, kind)
            for label, kind, target in self.links
            if target == DEPRECATED_DOCTYPE
        )
        self.assertEqual(
            offenders,
            [],
            "{0} is deprecated in favour of Safety Round but is still offered as a "
            "workspace entry point by: {1}".format(DEPRECATED_DOCTYPE, offenders),
        )


if __name__ == "__main__":
    unittest.main()
