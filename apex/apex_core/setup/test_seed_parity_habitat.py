# Copyright (c) 2026, AFMCO and contributors
"""Shape guards for the externalised Habitat seed JSON files.

The legacy ``habitat/*_seed.py`` modules that these files replaced were retired
in the seed consolidation (M-10/M-11), so the byte-identical parity comparisons
against the seeders' module constants are gone with them. What remains here are
the still-meaningful guards on the externalised JSON itself — DocType, natural
key, ``create_only`` flag, record count and per-record key presence — which the
data-driven loader (``apex_core.setup.seed.seed_all``) relies on. These are pure
(no site needed): they exercise only ``load_specs``.

The Auto Email Report seeder is deliberately NOT externalised: two of its fields
are runtime database lookups, not constants — ``email_to`` = the live
``Administrator`` user's email, and ``report_type`` = each Report's
``report_type`` resolved at install time. Static JSON cannot reproduce those, so
the seeder stays and we pin the reason here.
"""

import unittest

from apex.apex_core.setup.seed import load_specs


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
        """The claim above, asserted on the RECORD the seeder builds rather than on
        the source text that builds it: both fields must arrive from a live lookup,
        so a seeder that hardcoded either one fails here while any refactor of how
        it reads them stays green. Reads the shared engine, not the module wrapper, which
        carries the identical Habitat/Salis bodies.

        Site-free: the engine's ``frappe`` is swapped for a recording stub, so the
        two lookups are observed at the call boundary wherever they end up living.
        """
        from unittest.mock import MagicMock, patch

        from apex.apex_core.setup.seeders import auto_email_report_seed_base as engine

        live = {
            ("User", "Administrator", "email"): "live-admin@example.com",
            ("Report", "QA Digest", "report_type"): "Query Report",
        }
        built = []
        stub = MagicMock()
        stub.db.get_value.side_effect = lambda *args: live[args]
        # Nothing seeded yet, and the Report itself is installed.
        stub.db.exists.side_effect = lambda doctype, _filters: doctype == "Report"
        stub.get_doc.side_effect = lambda payload: built.append(payload) or MagicMock()

        with patch.object(engine, "frappe", stub):
            engine.seed_auto_email_reports_for([{"report": "QA Digest", "frequency": "Daily"}])

        self.assertEqual(len(built), 1, "one Auto Email Report must be created")
        self.assertEqual(built[0]["email_to"], "live-admin@example.com")
        self.assertEqual(built[0]["report_type"], "Query Report")


if __name__ == "__main__":
    unittest.main()
