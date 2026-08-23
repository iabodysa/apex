# Copyright (c) 2026, afmcoltd

"""The approver stamp must be unforgeable by the roles that raise the request.

``finance_approved_by`` and ``finance_approved_on`` record WHO released money, and the
payment router reads them. ``read_only`` on a field is a desk attribute and is not
enforced on save, so a role holding create/write could once post the stamp itself on an
insert at a non-gated status, where the finance gate early-returns and never inspects it.

The framework's own field-level permission closes it: both fields sit at ``permlevel: 1``
with read granted to ``All`` and write granted to NO role, so
``validate_higher_perm_levels`` (frappe/model/document.py:783) discards a caller-supplied
value before any controller method runs. ``_enforce_finance_gate`` runs after that
(document.py:306 then :309) and is therefore the only writer left.

CONTRACT: drop the permlevel from either field and the forge reopens; these tests fail
first. They are also the reason no hand-written reset guard is needed in the controller.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

FORGED_STAMP = "2026-01-01 00:00:00"


def _requester():
    """A user holding Fleet Supervisor — create and write, but no finance authority."""
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
        """The insert path and the save path take different branches through
        ``validate_higher_perm_levels`` (document.py:306 against :412), so proving one
        proves nothing about the other."""
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
        """The positive control. Write is denied to every role; READ is granted to All,
        so an auditor must still see who approved. Were the read row dropped too, the
        two tests above would pass while the field vanished from every screen."""
        meta = frappe.get_meta("Salis Payment Request")
        readable = {
            row.role
            for row in meta.permissions
            if row.permlevel == 1 and row.read
        }
        self.assertIn("All", readable)
        writable = [row.role for row in meta.permissions if row.permlevel == 1 and row.write]
        self.assertEqual(writable, [], "a role can write the stamp directly")
