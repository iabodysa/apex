"""Parity guards for the externalised Habitat record seeders.

These prove the data-driven JSON under ``tools/setup/data/habitat/`` did not
drift from the records the legacy ``*_seed.py`` modules insert. They are pure
(no site needed): they reconstruct each legacy seeder's *effective* record —
exactly the dict passed to ``frappe.get_doc({...}).insert()`` including child
rows appended in loops — from the seeder's own module-level data list, then
assert byte-identical equality against the JSON loaded via ``load_specs``.

Two seeders are externalised here:

- Assignment Rule  (assignment_rules_seed._RULES / _DAYS)
- Kanban Board     (kanban_seed._BOARDS)

The Auto Email Report seeder is deliberately NOT externalised: two of its
fields are runtime database lookups, not constants —
``email_to`` = the live ``Administrator`` user's email, and ``report_type`` =
each Report's ``report_type`` resolved at install time. Static JSON cannot
reproduce those without changing behaviour, so we assert the file is absent and
pin the reason here so the gap is intentional and visible.
"""

import json
import unittest

from apex_habitat.tools.setup.seed import load_specs


def _spec(doctype):
    specs = load_specs("habitat", only=[doctype])
    assert len(specs) == 1, f"expected exactly one spec for {doctype}, got {len(specs)}"
    return specs[0]


class TestAssignmentRuleParity(unittest.TestCase):
    """JSON must equal what assignment_rules_seed.seed_assignment_rules inserts."""

    def _legacy_effective_records(self):
        # Reconstruct the exact get_doc({...}) payload + appended child rows.
        from apex_habitat.habitat.assignment_rules_seed import _DAYS, _RULES

        records = []
        for cfg in _RULES:
            rec = {
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
            records.append(rec)
        return records

    def test_spec_metadata(self):
        spec = _spec("Assignment Rule")
        self.assertEqual(spec["doctype"], "Assignment Rule")
        self.assertEqual(spec["key"], "name")
        self.assertTrue(spec["create_only"])

    def test_record_count(self):
        spec = _spec("Assignment Rule")
        self.assertEqual(len(spec["records"]), 2)

    def test_records_byte_identical_to_legacy(self):
        spec = _spec("Assignment Rule")
        expected = self._legacy_effective_records()
        by_name = {r["name"]: r for r in spec["records"]}
        self.assertEqual(set(by_name), {r["name"] for r in expected})
        for exp in expected:
            self.assertEqual(by_name[exp["name"]], exp)

    def test_key_field_present_in_every_record(self):
        spec = _spec("Assignment Rule")
        for rec in spec["records"]:
            self.assertIn(spec["key"], rec)


class TestKanbanBoardParity(unittest.TestCase):
    """JSON must equal what kanban_seed.seed_kanban_boards inserts."""

    def _legacy_effective_records(self):
        from apex_habitat.habitat.kanban_seed import _BOARDS

        records = []
        for cfg in _BOARDS:
            rec = {
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
                        "order": json.dumps([]),
                    }
                    for column_name, indicator in cfg["columns"]
                ],
            }
            records.append(rec)
        return records

    def test_spec_metadata(self):
        spec = _spec("Kanban Board")
        self.assertEqual(spec["doctype"], "Kanban Board")
        # name == kanban_board_name (autoname: field:kanban_board_name); the
        # legacy guard's positional name lookup is equivalent to matching on
        # kanban_board_name, which is the field the record actually sets.
        self.assertEqual(spec["key"], "kanban_board_name")
        self.assertTrue(spec["create_only"])

    def test_record_count(self):
        spec = _spec("Kanban Board")
        self.assertEqual(len(spec["records"]), 3)

    def test_records_byte_identical_to_legacy(self):
        spec = _spec("Kanban Board")
        expected = self._legacy_effective_records()
        by_name = {r["kanban_board_name"]: r for r in spec["records"]}
        self.assertEqual(set(by_name), {r["kanban_board_name"] for r in expected})
        for exp in expected:
            self.assertEqual(by_name[exp["kanban_board_name"]], exp)

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
