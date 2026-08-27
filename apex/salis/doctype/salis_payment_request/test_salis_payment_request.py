# Copyright (c) 2026, afmcoltd


import frappe
from frappe.tests.utils import FrappeTestCase

FORGED_STAMP = "2026-01-01 00:00:00"


def _requester():
    email = "_test-salis-stamp-forge@example.com"
    if not frappe.db.exists("User", email):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Stamp Forge Probe",
                "send_welcome_email": 0,
            }
        )
        user.insert(ignore_permissions=True)
        user.add_roles("Fleet Supervisor")
    return email


class TestTheFinanceStampIsServerOwned(FrappeTestCase):
    def setUp(self):
        self.requester = _requester()
        frappe.set_user(self.requester)
        self.addCleanup(frappe.set_user, "Administrator")

    def _forged_draft(self):
        return frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Other",
                "amount": 100,
                "status": "Draft",
                "finance_approved_by": "Administrator",
                "finance_approved_on": FORGED_STAMP,
            }
        )

    def test_a_requester_cannot_post_the_approver_on_an_insert(self):
        doc = self._forged_draft()
        doc.insert()
        self.addCleanup(frappe.delete_doc, doc.doctype, doc.name, force=True, ignore_permissions=True)

        self.assertFalse(doc.finance_approved_by, "the approver identity survived an insert")
        self.assertFalse(doc.finance_approved_on, "the approval time survived an insert")

    def test_a_requester_cannot_post_the_approver_on_a_later_save(self):
        doc = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Other",
                "amount": 100,
                "status": "Draft",
            }
        )
        doc.insert()
        self.addCleanup(frappe.delete_doc, doc.doctype, doc.name, force=True, ignore_permissions=True)

        doc.finance_approved_by = "Administrator"
        doc.finance_approved_on = FORGED_STAMP
        doc.save()

        self.assertFalse(doc.finance_approved_by, "the approver identity survived a save")
        self.assertFalse(doc.finance_approved_on, "the approval time survived a save")

    def test_the_stamp_is_still_readable(self):
        meta = frappe.get_meta("Salis Payment Request")
        readable = {
            row.role
            for row in meta.permissions
            if row.permlevel == 1 and row.read
        }
        self.assertIn("All", readable)
        writable = [row.role for row in meta.permissions if row.permlevel == 1 and row.write]
        self.assertEqual(writable, [], "a role can write the stamp directly")
