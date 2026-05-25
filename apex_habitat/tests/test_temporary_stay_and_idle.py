# Copyright (c) 2026, AFMCO and contributors
"""v0.8.5 — Temporary-stay validation on Accommodation Assignment and the Idle
Resident Report status flow (schema groundwork; no automation yet)."""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestTemporaryStayAndIdle(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": self.cc}).insert(ignore_permissions=True).name
        self.employee = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                        "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name
        self.project = frappe.get_doc({"doctype": "Project", "project_name": "P " + _h()}).insert(ignore_permissions=True).name

    def _assignment(self, stay_type, expected=None):
        return frappe.get_doc({
            "doctype": "Accommodation Assignment", "naming_series": "ACC-ASG-.YYYY.-.#####",
            "employee": self.employee, "project": self.project, "building": self.building,
            "cost_center": self.cc, "check_in_date": "2026-05-01",
            "stay_type": stay_type, "expected_checkout_date": expected,
        })

    def test_temporary_requires_expected_checkout_date(self):
        with self.assertRaises(frappe.ValidationError):
            self._assignment("Temporary").insert(ignore_permissions=True)

    def test_temporary_expected_date_after_checkin(self):
        with self.assertRaises(frappe.ValidationError):
            self._assignment("Temporary", "2026-04-20").insert(ignore_permissions=True)

    # --- Idle Resident Report ------------------------------------------------
    def _idle(self, **kw):
        doc = frappe.get_doc({
            "doctype": "Idle Resident Report", "naming_series": "IDLE-.YYYY.-.####",
            "employee": self.employee, "building": self.building,
            "reason_category": "New Hire", "responsible_department": "Operations",
            "status": "Open", **kw})
        return doc

    def test_idle_resolve_requires_notes(self):
        doc = self._idle().insert(ignore_permissions=True)
        doc.status = "Resolved"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_idle_rejects_duplicate_open_report(self):
        self._idle().insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            self._idle().insert(ignore_permissions=True)
