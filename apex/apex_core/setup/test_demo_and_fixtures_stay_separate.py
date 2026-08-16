# Copyright (c) 2026, AFMCO and contributors
"""No DocType may be shipped as a fixture and built by the demo at the same time.

The two mechanisms answer opposite questions about the same verb "ship", and mixing them
breaks the one the operator can see.

A FIXTURE is the app's own data. ``sync_fixtures`` re-imports it on every ``bench migrate``
(frappe/utils/fixtures.py), which is exactly right for a Workflow or an Issue Type: the app
owns it, and a site that drifted from it should be pulled back.

DEMO DATA is the operator's to delete. ``clear_demo_data`` removes every row the build made
and the flag goes false. Ship any of it as a fixture and the next migrate imports it again —
the removal button then clears a screen that refills itself, which is worse than no button.

So the check is one line of set arithmetic, and the population check beside it is what stops
it passing on an empty read: a typo in either list would otherwise make the intersection
empty and the guard green.
"""

import ast
import re
import unittest
from pathlib import Path

import apex

APP_ROOT = Path(apex.__file__).resolve().parent


def _fixture_doctypes():
    """Every ``dt`` named in hooks.fixtures, read as text rather than imported.

    The list interpolates module constants (``list(WORKFLOW_STATES)``), so ast.literal_eval
    refuses it; the doctype names themselves are plain string literals and are what this
    grades.
    """
    source = (APP_ROOT / "hooks.py").read_text(encoding="utf-8")
    block = re.search(r"^fixtures = \[(.*?)\n\]", source, re.S | re.M)
    return set(re.findall(r'"dt":\s*"([^"]+)"', block.group(1) if block else ""))


def _demo_doctypes():
    source = (APP_ROOT / "apex_core" / "setup" / "demo.py").read_text(encoding="utf-8")
    block = re.search(r"^DEMO_DOCTYPES = (\(.*?\n\))", source, re.S | re.M)
    return set(ast.literal_eval(block.group(1))) if block else set()


class TestDemoAndFixturesStaySeparate(unittest.TestCase):
    def test_no_doctype_is_both_a_fixture_and_demo_data(self):
        overlap = sorted(_fixture_doctypes() & _demo_doctypes())
        self.assertEqual(
            overlap,
            [],
            "shipped as a fixture AND built by the demo, so migrate restores what the "
            f"removal deletes: {overlap}",
        )

    def test_both_lists_were_actually_read(self):
        """The positive control: an empty read makes the intersection empty and green."""
        self.assertGreater(len(_fixture_doctypes()), 3, "hooks.fixtures read as empty")
        self.assertGreater(len(_demo_doctypes()), 20, "DEMO_DOCTYPES read as empty")


if __name__ == "__main__":
    unittest.main()
