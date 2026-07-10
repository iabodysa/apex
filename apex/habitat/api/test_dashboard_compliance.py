# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Compliance % Custom Number Card method get_compliance_percent.

The card reports Completed / (all non-Cancelled) Scheduled Task Instances as a
percent. Instances are inserted directly with ignore_links/ignore_mandatory (the
same direct approach the sibling dashboard tests use) so the cases are
deterministic without a Scheduled Task Template master chain. The percentage is a
whole-site ratio, so we assert the {value, ...df} dict contract (shape) plus the
ratio computed from a direct, formula-mirroring count rather than a brittle
absolute number."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.dashboard import get_compliance_percent


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestDashboardCompliance(FrappeTestCase):
    def setUp(self):
        self._names = []

    def _instance(self, status):
        """Insert one Scheduled Task Instance forced to a given status."""
        doc = frappe.get_doc({
            "doctype": "Scheduled Task Instance",
            "naming_series": "STI-.YYYY.-.####",
            "template": "STT-" + _h(),
            "due_date": "2026-06-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        # status is set after insert so a validate default cannot override it.
        frappe.db.set_value("Scheduled Task Instance", doc.name, "status", status,
                            update_modified=False)
        self._names.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._names:
            frappe.delete_doc("Scheduled Task Instance", name, force=True,
                              ignore_permissions=True)

    def _expected_percent(self):
        """Recompute the card's own formula directly from the DB."""
        total = frappe.db.count("Scheduled Task Instance",
                                {"status": ["not in", ["Cancelled"]]})
        if not total:
            return 100.0
        completed = frappe.db.count("Scheduled Task Instance", {"status": "Completed"})
        return round((completed / total) * 100, 2)

    def test_returns_number_card_dict_contract(self):
        """Custom Number Card contract: {value: <number>, ...df} — never a bare
        scalar (a scalar renders the value but drops the format docfield)."""
        res = get_compliance_percent()
        self.assertIsInstance(res, dict, "Custom Number Card returns a dict, not a scalar")
        self.assertIn("value", res, "the number must live under the 'value' key")
        self.assertIsInstance(res["value"], (int, float))
        self.assertEqual(res.get("fieldtype"), "Percent")
        self.assertEqual(res.get("precision"), 2)

    def test_value_matches_completed_over_non_cancelled(self):
        """value equals Completed / non-Cancelled * 100, and Cancelled rows are
        excluded from the denominator (they would otherwise depress the ratio)."""
        self._instance("Completed")
        self._instance("Completed")
        self._instance("In Progress")
        self._instance("Cancelled")  # excluded from numerator AND denominator
        self.assertEqual(get_compliance_percent()["value"], self._expected_percent())

    def test_cancelled_rows_never_break_the_ratio(self):
        """Cancelled instances are excluded from the denominator and never raise
        ZeroDivisionError; value tracks the formula mirror regardless of how many
        pre-existing rows are on site (the empty-site 100.0 fallback is the
        denominator==0 case of that same mirror)."""
        self._instance("Cancelled")
        res = get_compliance_percent()
        self.assertIsInstance(res["value"], (int, float))
        self.assertEqual(res["value"], self._expected_percent())
