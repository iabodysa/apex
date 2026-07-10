# Copyright (c) 2026, AFMCO and contributors
"""Ownership scope for the My Custody Acknowledgment web-form context.

The form takes an ``?issue=`` query param and pre-fills it into the page. Without
an ownership check (R5) any authenticated caller could pass another employee's
Custody Issue docname and have it rendered. The picklist's already-acknowledged
exclusion set (R6) is built on ``frappe.get_all`` (which forces
``ignore_permissions``), so an unfiltered query would read every building's
acknowledgments cross-tenant.

These pin:
  * R5 — a foreign ``?issue=`` is NOT echoed into ``prefill_issue`` (it falls back
    to the holder's own first issue, or blank);
  * R5 — the holder's OWN ``?issue=`` IS honoured;
  * R6 — the acknowledged-exclusion lookup is scoped to the holder's own issues.
"""

from __future__ import annotations

import frappe

from apex_habitat.habitat.web_form.my_custody_acknowledgment.my_custody_acknowledgment import (
    get_context,
)
from apex_habitat.tests.test_utils import ApexHabitatTestCase


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class _Ctx:
    """Minimal stand-in for the web-form context (an attribute bag)."""


class TestMyCustodyAckContext(ApexHabitatTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.building = cls._building()
        cls.user_a, cls.emp_a = cls._employee_user()
        cls.user_b, cls.emp_b = cls._employee_user()
        # A's own open issue and B's own open issue (the foreign one).
        cls.issue_a = cls._issue(cls.emp_a)
        cls.issue_b = cls._issue(cls.emp_b)

    @classmethod
    def _building(cls):
        doc = frappe.get_doc(
            {"doctype": "Building", "building_name": "ACK-" + _h()}
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _employee_user(cls):
        email = "ack-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Ack",
                "send_welcome_email": 0,
                "roles": [{"role": "Employee"}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.delete_doc, "User", email, force=True, ignore_permissions=True)
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": "Ack " + _h(),
                "first_name": "Ack",
                "user_id": email,
                "status": "Active",
            }
        )
        emp.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Employee", emp.name, force=True, ignore_permissions=True
        )
        return email, emp.name

    @classmethod
    def _issue(cls, employee):
        doc = frappe.get_doc(
            {
                "doctype": "Custody Issue",
                "issue_date": frappe.utils.today(),
                "building": cls.building,
                "issued_to_employee": employee,
            }
        )
        # ignore_validate: skip the Custody Issue write controller (which requires a
        # child item row). These tests pin the web-form context ownership scope, which
        # reads only issued_to_employee — the items the controller mandates are irrelevant.
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value("Custody Issue", doc.name, {"docstatus": 1, "status": "Issued"})
        cls.addClassCleanup(
            lambda n=doc.name: (
                frappe.db.set_value("Custody Issue", n, "docstatus", 0),
                frappe.delete_doc("Custody Issue", n, force=True, ignore_permissions=True),
            )
        )
        return doc.name

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        self.addCleanup(frappe.form_dict.pop, "issue", None)

    def _context_as(self, user, issue_param=None):
        frappe.set_user(user)
        if issue_param is not None:
            frappe.form_dict["issue"] = issue_param
        else:
            frappe.form_dict.pop("issue", None)
        ctx = _Ctx()
        get_context(ctx)
        return ctx

    # ---- R5 --------------------------------------------------------------
    def test_foreign_issue_param_not_prefilled(self):
        """A's session passes B's issue docname — it must NOT be echoed back."""
        ctx = self._context_as(self.user_a, issue_param=self.issue_b)
        self.assertNotEqual(
            ctx.prefill_issue, self.issue_b, "another employee's issue must never be pre-filled"
        )
        # Falls back to A's own issue (A has exactly one open, unacknowledged issue).
        self.assertEqual(ctx.prefill_issue, self.issue_a)

    def test_own_issue_param_is_honoured(self):
        ctx = self._context_as(self.user_a, issue_param=self.issue_a)
        self.assertEqual(ctx.prefill_issue, self.issue_a, "the holder's own issue must pre-fill")

    def test_unknown_issue_param_falls_back(self):
        ctx = self._context_as(self.user_a, issue_param="Custody Issue-DOES-NOT-EXIST")
        self.assertEqual(ctx.prefill_issue, self.issue_a)

    # ---- R6 --------------------------------------------------------------
    def test_picklist_is_own_issues_only(self):
        """A's picklist contains A's issue and never B's."""
        ctx = self._context_as(self.user_a)
        names = {ci.name for ci in ctx.my_custody_issues}
        self.assertIn(self.issue_a, names)
        self.assertNotIn(self.issue_b, names, "another employee's issue must never appear")
