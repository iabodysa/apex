# Copyright (c) 2026, AFMCO and contributors
"""Shape guards for the externalised Salis seed JSON files.

The legacy ``salis/*_seed.py`` modules that these files replaced were retired in
the seed consolidation (M-10/M-11), so the byte-identical parity comparisons
against the seeders' module constants are gone with them. What remains are the
still-meaningful guards on the externalised JSON itself — DocType, natural key,
``create_only`` flag and record count — which the data-driven loader
(``apex_core.setup.seed.seed_all``) relies on. Pure tests: they exercise only
``load_specs`` (no ``frappe`` site needed).

Auto Email Report is intentionally NOT externalised: its seeder sets two per-site
runtime fields — ``email_to`` (Administrator's configured email) and
``report_type`` (a ``frappe.db.get_value`` lookup) — so its inserted record is
not statically reproducible. The test asserts the file's deliberate absence so
the decision is documented and enforced.
"""

import os
import unittest

from apex_habitat.apex_core.setup.seed import DATA_ROOT, load_specs


def _spec(doctype):
    specs = load_specs("salis", only=[doctype])
    assert len(specs) == 1, f"expected exactly one spec for {doctype}, got {len(specs)}"
    return specs[0]


class TestSalisEmailTemplateSpec(unittest.TestCase):
    def test_spec_shape(self):
        spec = _spec("Email Template")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])
        self.assertEqual(len(spec["records"]), 3)
        for rec in spec["records"]:
            self.assertIn("name", rec)


class TestSalisAssignmentRuleSpec(unittest.TestCase):
    def test_spec_shape(self):
        spec = _spec("Assignment Rule")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])
        self.assertEqual(len(spec["records"]), 2)
        for rec in spec["records"]:
            self.assertIn("name", rec)


class TestSalisKanbanBoardSpec(unittest.TestCase):
    def test_spec_shape(self):
        spec = _spec("Kanban Board")
        # [#iy63b3]
        self.assertEqual(spec["key"], "kanban_board_name")
        self.assertTrue(spec["create_only"])
        self.assertEqual(len(spec["records"]), 2)
        for rec in spec["records"]:
            self.assertIn("kanban_board_name", rec)


class TestSalisAutoEmailReportNotExternalised(unittest.TestCase):
    def test_auto_email_report_is_not_externalised(self):
        # [#3cpddz]
        self.assertEqual(load_specs("salis", only=["Auto Email Report"]), [])
        self.assertFalse(
            os.path.exists(os.path.join(DATA_ROOT, "salis", "auto_email_report.json")),
            "Auto Email Report must not be externalised: email_to/report_type are runtime values",
        )


if __name__ == "__main__":
    unittest.main()
