# Copyright (c) 2026, AFMCO and contributors
"""Custody Damage Assessment's own contract: what it refuses on save, and what the
whitelisted ``get_deduction_status`` reports about a linked Additional Salary.

WHAT THIS FILE NO LONGER COVERS, and why. The controller once posted an Additional
Salary from ``on_submit`` against a rule held on the retired salary-deduction policy
Single. That path is gone: ``on_submit`` now returns ``None``
(custody_damage_assessment.py:107), ``get_damage_rule`` exists nowhere in the app, and
that DocType was deleted by
``apex/patches/v2_6/converge_native_support_and_recovery.py:175``. The two methods that
drove it were removed rather than repaired — there is no longer a subject to repair them
against.

``deduction_entry`` therefore has no writer in product code today, so the status endpoint
below is exercised with the link set by hand. ``on_cancel`` and ``before_cancel``, which
undo and guard that link, are likewise unreachable from the app's own submit path."""
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


class TestCustodyDamageAssessment(FrappeTestCase):

    def test_create_valid_assessment(self):
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)

    def test_missing_assessment_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_items_raises(self):
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import validate

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_deduction_status_not_created_when_no_entry(self):
        """No linked Additional Salary -> 'Not Created' so the manager can tell
        the deduction never flowed (disabled / below threshold)."""
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        result = get_deduction_status(doc.name)
        self.assertIsNone(result["entry"])
        self.assertEqual(result["status"], "Not Created")
        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)

    def test_deduction_status_reflects_additional_salary_docstatus(self):
        """A linked draft Additional Salary reports 'Draft'; the indicator
        reflects the linked record's live docstatus, not a stored copy."""
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        company = frappe.db.get_value("Company", {}, "name") or "_Test Company"
        component = "QA-DMG-" + frappe.generate_hash(length=12)
        salary_component = frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": component,
            "type": "Deduction",
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)

        add_sal = frappe.get_doc({
            "doctype": "Additional Salary",
            "employee": "QA-EMP",
            "salary_component": salary_component.name,
            "amount": 150,
            "payroll_date": "2026-07-10",
            "company": company,
            "currency": "SAR",
        })
        add_sal.flags.ignore_validate = True
        add_sal.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "deduction_entry": add_sal.name,
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)

        result = get_deduction_status(doc.name)
        self.assertEqual(result["entry"], add_sal.name)
        self.assertEqual(result["status"], "Draft")

        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Additional Salary", add_sal.name, force=True, ignore_permissions=True)

    def test_get_deduction_status_denied_without_cda_read(self):
        """IDOR: the whitelisted get_deduction_status must gate per-doc
        read. A user with none of the CDA-read roles raises PermissionError so
        they cannot probe another worker's deduction status; a manager (here
        Administrator, who short-circuits has_permission) still gets the dict."""
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)

        email = "qa-cda-noread-" + frappe.generate_hash(length=12) + "@example.com"
        no_read_user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "QA NoRead",
            "send_welcome_email": 0,
            "roles": [],
        }).insert(ignore_permissions=True)

        try:
            frappe.set_user(no_read_user.name)
            with self.assertRaises(frappe.PermissionError):
                get_deduction_status(doc.name)
        finally:
            frappe.set_user("Administrator")

        result = get_deduction_status(doc.name)
        self.assertEqual(result["status"], "Not Created")

        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)
        frappe.delete_doc("User", no_read_user.name, force=True, ignore_permissions=True)
