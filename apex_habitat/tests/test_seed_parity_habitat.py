"""Shape guards for the externalised Habitat seed JSON files.

The legacy ``habitat/*_seed.py`` modules that these files replaced were retired
in the seed consolidation (M-10/M-11), so the byte-identical parity comparisons
against the seeders' module constants are gone with them. What remains here are
the still-meaningful guards on the externalised JSON itself — DocType, natural
key, ``create_only`` flag, record count and per-record key presence — which the
data-driven loader (``tools.setup.seed.seed_all``) relies on. These are pure
(no site needed): they exercise only ``load_specs``.

The Auto Email Report seeder is deliberately NOT externalised: two of its fields
are runtime database lookups, not constants — ``email_to`` = the live
``Administrator`` user's email, and ``report_type`` = each Report's
``report_type`` resolved at install time. Static JSON cannot reproduce those, so
the seeder stays and we pin the reason here.
"""

import unittest

from apex_habitat.tools.setup.seed import load_specs


def _spec(doctype):
    specs = load_specs("habitat", only=[doctype])
    assert len(specs) == 1, f"expected exactly one spec for {doctype}, got {len(specs)}"
    return specs[0]


class TestAssignmentRuleSpec(unittest.TestCase):
    def test_spec_metadata(self):
        spec = _spec("Assignment Rule")
        self.assertEqual(spec["doctype"], "Assignment Rule")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])

    def test_record_count(self):
        self.assertEqual(len(_spec("Assignment Rule")["records"]), 2)

    def test_key_field_present_in_every_record(self):
        spec = _spec("Assignment Rule")
        for rec in spec["records"]:
            self.assertIn(spec["key"], rec)


class TestKanbanBoardSpec(unittest.TestCase):
    def test_spec_metadata(self):
        spec = _spec("Kanban Board")
        self.assertEqual(spec["doctype"], "Kanban Board")
        # Kanban Board auto-names from kanban_board_name, so the existence guard
        # matches on that field rather than ``name``.
        self.assertEqual(spec["key"], "kanban_board_name")
        self.assertTrue(spec["create_only"])

    def test_record_count(self):
        self.assertEqual(len(_spec("Kanban Board")["records"]), 3)

    def test_key_field_present_in_every_record(self):
        spec = _spec("Kanban Board")
        for rec in spec["records"]:
            self.assertIn(spec["key"], rec)


class TestAutoEmailReportNotExternalised(unittest.TestCase):
    """Auto Email Report stays a code seeder: two of its fields are runtime DB
    lookups (not constants), so static JSON cannot reproduce its behaviour."""

    def test_no_externalised_json_for_auto_email_report(self):
        self.assertEqual(load_specs("habitat", only=["Auto Email Report"]), [])

    def test_legacy_seeder_resolves_dynamic_fields(self):
        # Pin the reason: the seeder builds email_to and report_type from the
        # live database, so they are not static constants.
        import inspect

        from apex_habitat.habitat import auto_email_reports_seed

        src = inspect.getsource(auto_email_reports_seed.seed_auto_email_reports)
        self.assertIn('frappe.db.get_value("User", "Administrator", "email")', src)
        self.assertIn('frappe.db.get_value("Report", cfg["report"], "report_type")', src)


if __name__ == "__main__":
    unittest.main()
