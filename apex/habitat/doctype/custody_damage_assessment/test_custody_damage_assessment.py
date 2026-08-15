# Copyright (c) 2026, AFMCO and contributors
"""Custody Damage Assessment's own contract: what it refuses on save, what it totals, and
the payroll document it must NOT raise.

The controller once posted an Additional Salary from ``on_submit`` against a rule held on
the retired salary-deduction policy Single. That policy DocType was deleted by
``apex/patches/v2_6/converge_native_support_and_recovery.py``, and the rule reader went with
it, leaving a ``deduction_entry`` link that nothing wrote and two cancel hooks undoing a
document that was never created. The removal is now complete: the field is gone from the
DocType and the assessment values the damage without recovering it. Recovery from a worker
has exactly one chain in this app — the native HRMS Employee Advance one — and it is not
reached from here, so the tests below pin the absence rather than a status indicator."""
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

    def test_deduction_entry_is_absent_from_the_doctype(self):
        """The link to Additional Salary is gone from the DocType, not merely unwritten.

        A read-only Link that nothing writes is a field an operator can only ever see
        blank, and a promise the module cannot keep. It went with the writer.
        """
        meta = frappe.get_meta("Custody Damage Assessment")
        self.assertIsNone(
            meta.get_field("deduction_entry"),
            "deduction_entry has no writer anywhere in the app, so it must not be a field",
        )

    def test_controller_exposes_no_payroll_lifecycle(self):
        """No submit hook, no cancel guard, no cancel reversal, no status endpoint.

        Each of those existed only to serve the deleted deduction: before_cancel guarded a
        posting nothing made, on_cancel undid a document nothing created, and the endpoint
        reported the state of a link nothing set.
        """
        from apex.habitat.doctype.custody_damage_assessment import custody_damage_assessment

        for gone in ("on_submit", "before_cancel", "on_cancel", "get_deduction_status"):
            self.assertFalse(
                hasattr(custody_damage_assessment, gone),
                f"{gone} belongs to the removed deduction path and must not survive it",
            )

    def test_hooks_no_longer_register_the_retired_deduction_lifecycle(self):
        """``hooks.py`` must stop naming the three functions that went with the field.

        A registration that outlives its handler is not cosmetic: Frappe resolves the
        handler lazily, inside ``Document.hook`` (frappe/model/document.py:1364-1371), so
        the first real submit of an assessment raises AttributeError rather than failing
        at import. ``hooks.py`` is a one-writer-at-a-time shared file, so the trim itself
        belongs to whoever holds it — this asserts the contract from here.
        """
        events = frappe.get_doc_hooks().get("Custody Damage Assessment", {})
        self.assertEqual(
            sorted(events), ["validate"],
            "hooks.py still registers on_submit / before_cancel / on_cancel for Custody "
            "Damage Assessment; those handlers no longer exist",
        )
