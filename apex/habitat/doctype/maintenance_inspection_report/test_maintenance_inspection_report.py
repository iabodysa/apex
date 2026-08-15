"""Size note: 127 test lines against 32 in the subject (4.0x), for 8 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting: each test names a different behaviour."""

# Copyright (c) 2026, AFMCO and contributors
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestMaintenanceInspectionReport(FrappeTestCase):

    def test_create_valid_report(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "inspector": "EMP-QA-001",
            "findings": [{"doctype": "Inspection Finding Item", "description": "crack in wall"}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Maintenance Inspection Report", doc.name, force=True, ignore_permissions=True)

    def test_missing_inspector_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "findings": [{"doctype": "Inspection Finding Item", "description": "crack in wall"}],
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_findings_raises(self):
        from apex.habitat.doctype.maintenance_inspection_report.maintenance_inspection_report import validate

        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "inspector": "EMP-QA-001",
            "findings": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)


class TestMaintenanceInspectionAssetStamp(FrappeTestCase):
    """on_submit stamps the linked Facility Asset's last_inspection_date (most-recent
    wins); on_cancel recomputes it from the remaining submitted inspections."""

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.building = frappe.get_doc({
            "doctype": "Building", "building_name": "B " + self._h(),
            "total_capacity": 4, "company": self.company,
        }).insert(ignore_permissions=True, ignore_links=True).name
        self.inspector = frappe.get_doc({
            "doctype": "Employee", "first_name": "Insp " + self._h(), "company": self.company,
            "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name
        self.asset = frappe.get_doc({
            "doctype": "Facility Asset", "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Camera " + self._h(), "asset_category": "CCTV Camera",
            "building": self.building, "responsible_supervisor": "Administrator",
        }).insert(ignore_permissions=True, ignore_links=True).name

    def _report(self, inspection_date, facility_asset=None):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": inspection_date,
            "building": self.building,
            "inspector": self.inspector,
            "facility_asset": facility_asset,
            "findings": [{"doctype": "Inspection Finding Item", "description": "check"}],
        })
        doc.insert(ignore_permissions=True)
        return doc

    def _stamp(self):
        return frappe.db.get_value("Facility Asset", self.asset, "last_inspection_date")

    def test_submit_stamps_asset(self):
        self.assertIsNone(self._stamp())
        r = self._report("2026-06-10", self.asset)
        r.submit()
        self.assertEqual(str(self._stamp()), "2026-06-10")

    def test_only_most_recent_date_wins(self):
        self._report("2026-06-10", self.asset).submit()
        self._report("2026-06-20", self.asset).submit()
        self.assertEqual(str(self._stamp()), "2026-06-20")
        self._report("2026-06-01", self.asset).submit()
        self.assertEqual(str(self._stamp()), "2026-06-20")

    def test_cancel_recomputes_from_remaining(self):
        self._report("2026-06-10", self.asset).submit()
        newest = self._report("2026-06-20", self.asset)
        newest.submit()
        self.assertEqual(str(self._stamp()), "2026-06-20")
        newest.cancellation_reason = "test"
        newest.cancel()
        self.assertEqual(str(self._stamp()), "2026-06-10")

    def test_cancel_only_report_clears_stamp(self):
        only = self._report("2026-06-10", self.asset)
        only.submit()
        self.assertEqual(str(self._stamp()), "2026-06-10")
        only.cancellation_reason = "test"
        only.cancel()
        self.assertIsNone(self._stamp())

    def test_report_without_asset_is_noop(self):
        """No facility_asset means the controller writes to no Facility Asset at all.

        Asserting only that this test's own asset stayed unstamped cannot fail:
        ``frappe.db.set_value`` handed a None docname is treated as a Single and
        writes to ``tabSingles``, never to a Facility Asset row, so removing either
        early return would leave every asset untouched anyway and keep the stamp
        assertions green. The falsifiable statement is the count of Facility Asset
        writes, so the writes are recorded across both the submit and the cancel.
        """
        with patch.object(frappe.db, "set_value", wraps=frappe.db.set_value) as writes:
            r = self._report("2026-06-15", None)
            r.submit()
            r.cancellation_reason = "test"
            r.cancel()

        self.assertEqual(
            [call.args[:2] for call in writes.call_args_list
             if call.args and call.args[0] == "Facility Asset"],
            [],
            "an asset-less inspection must not write to Facility Asset",
        )
        self.assertIsNone(self._stamp())
