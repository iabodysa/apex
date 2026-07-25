# Copyright (c) 2026, AFMCO and contributors
"""submit_round rejects a non-allowlisted cadence BEFORE the savepoint.

cadence feeds the savepoint identifier in _create_round
(f"safety_checklist_round_{frappe.scrub(cadence)}"), so a value carrying a quote
or semicolon must be rejected up-front with a clean ValidationError — never
reaching frappe.db.savepoint, _create_round, or any Safety Round insert. These
tests pin that the allowlist guard fires first.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.api.safety_checklist import submit_round
from apex.tests.factories import make_building, make_company


class TestSubmitRoundCadenceGuard(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        make_company()
        self.building = make_building(
            name=f"CadGuard Bldg {self._testMethodName}"
        ).name

    def _lines(self):
        # [#mbaysw]
        task = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": f"CG-{self._testMethodName[:8]}",
                "task_title": "Cadence Guard Task",
                "department": "Fire Safety",
                "frequency": "Daily",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name
        return [{"task": task, "execution_status": "Good"}]

    def test_quote_cadence_raises_clean_validation_error(self):
        # [#pcq8ff]
        with self.assertRaises(frappe.ValidationError):
            submit_round(self.building, "Daily'; DROP", today(), self._lines())

    def test_semicolon_cadence_raises_clean_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            submit_round(self.building, "Weekly; SELECT 1", today(), self._lines())

    def test_bad_cadence_never_reaches_the_savepoint(self):
        # [#ha4t43]
        before = frappe.db.count("Safety Round", {"building": self.building})
        with patch(
            "apex.habitat.api.safety_checklist.frappe.db.savepoint"
        ) as mock_savepoint:
            with self.assertRaises(frappe.ValidationError):
                submit_round(self.building, "x'; DROP TABLE", today(), self._lines())
        mock_savepoint.assert_not_called()
        after = frappe.db.count("Safety Round", {"building": self.building})
        self.assertEqual(after, before, "no round may be created for a bad cadence")

    def test_valid_cadence_still_accepted(self):
        # [#oldwez]
        out = submit_round(self.building, "Daily", today(), self._lines())
        self.assertTrue(out["ok"])
        self.assertEqual(
            frappe.db.get_value("Safety Round", out["safety_round"], "docstatus"), 1
        )
