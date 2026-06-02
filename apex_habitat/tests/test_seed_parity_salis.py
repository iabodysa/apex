"""Parity guards for the externalised Salis seed JSON files.

Each test reconstructs the *effective* records the legacy ``salis/*_seed.py``
module would pass to ``frappe.get_doc({...}).insert()`` (constants + loop output)
and asserts the externalised JSON under ``tools/setup/data/salis/`` is an exact,
byte-identical match — same ``key``, same fieldnames, same values, same child
rows in the same order.

Pure tests: they exercise only ``load_specs`` (no ``frappe`` site needed) and the
plain Python constants of the legacy seeders.

Auto Email Report is intentionally NOT externalised: its seeder sets two
per-site runtime fields — ``email_to`` (Administrator's configured email, with a
fallback) and ``report_type`` (a ``frappe.db.get_value`` lookup) — so its inserted
record is not statically reproducible. This mirrors the habitat module, whose
``auto_email_reports_seed.py`` is likewise left un-externalised. The test asserts
the file's deliberate absence so the decision is documented and enforced.
"""

import os
import unittest

from apex_habitat.tools.setup.seed import DATA_ROOT, load_specs

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _spec(doctype):
    specs = load_specs("salis", only=[doctype])
    assert len(specs) == 1, f"expected exactly one spec for {doctype}, got {len(specs)}"
    return specs[0]


class TestSalisEmailTemplateParity(unittest.TestCase):
    def test_email_template_parity_with_legacy_seeder(self):
        from apex_habitat.salis.email_templates_seed import _TEMPLATES

        spec = _spec("Email Template")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])

        # The seeder's effective insert payload for each template.
        expected = [
            {
                "name": t["name"],
                "subject": t["subject"],
                "use_html": 1,
                "response_html": t["response_html"],
            }
            for t in _TEMPLATES
        ]
        self.assertEqual(spec["records"], expected)


class TestSalisAssignmentRuleParity(unittest.TestCase):
    def test_assignment_rule_parity_with_legacy_seeder(self):
        from apex_habitat.salis.assignment_rules_seed import _RULES

        spec = _spec("Assignment Rule")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])

        expected = [
            {
                "name": cfg["name"],
                "document_type": cfg["document_type"],
                "rule": cfg["rule"],
                "disabled": 1,
                "description": cfg["description"],
                "assign_condition": cfg["assign_condition"],
                "priority": 0,
                "users": [{"user": "Administrator"}],
                "assignment_days": [{"day": day} for day in _DAYS],
            }
            for cfg in _RULES
        ]
        self.assertEqual(spec["records"], expected)


class TestSalisKanbanBoardParity(unittest.TestCase):
    def test_kanban_board_parity_with_legacy_seeder(self):
        from apex_habitat.salis.kanban_seed import _BOARDS

        spec = _spec("Kanban Board")
        # Kanban Board auto-names from kanban_board_name, so the seeder's
        # exists()-by-name guard is matched on the kanban_board_name field.
        self.assertEqual(spec["key"], "kanban_board_name")
        self.assertTrue(spec["create_only"])

        expected = [
            {
                "kanban_board_name": cfg["name"],
                "reference_doctype": cfg["reference_doctype"],
                "field_name": cfg["field_name"],
                "private": 0,
                "show_labels": 1,
                "filters": "[]",
                "columns": [
                    {
                        "column_name": column_name,
                        "status": "Active",
                        "indicator": indicator,
                        "order": "[]",
                    }
                    for column_name, indicator in cfg["columns"]
                ],
            }
            for cfg in _BOARDS
        ]
        self.assertEqual(spec["records"], expected)


class TestSalisAutoEmailReportNotExternalised(unittest.TestCase):
    def test_auto_email_report_is_not_externalised(self):
        # The seeder sets per-site runtime fields (email_to, report_type), so it
        # is not statically reproducible and is deliberately left as a seeder.
        self.assertEqual(load_specs("salis", only=["Auto Email Report"]), [])
        self.assertFalse(
            os.path.exists(os.path.join(DATA_ROOT, "salis", "auto_email_report.json")),
            "Auto Email Report must not be externalised: email_to/report_type are runtime values",
        )


if __name__ == "__main__":
    unittest.main()
