# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_project


def _user(first_name, roles=()):
    email = "_t_mct_" + frappe.generate_hash(length=6) + "@example.com"
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "send_welcome_email": 0,
        }
    )
    doc.insert(ignore_permissions=True)
    if roles:
        doc.add_roles(*roles)
    return email


def _transfer(**overrides):
    fields = {
        "doctype": "Movement Cost Transfer",
        "transfer_type": "Fuel",
        "amount": 500,
        "from_project": make_project("_T-MCT Project From"),
        "to_project": make_project("_T-MCT Project To"),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _pending(**overrides):
    doc = _transfer(**overrides).insert(ignore_permissions=True)
    apply_workflow(doc, "Submit for Approval")
    return doc


def _approved(**overrides):
    doc = _pending(**overrides)
    approver = _user("_T-MCT Fleet Manager", roles=("Fleet Manager",))
    frappe.set_user(approver)
    try:
        apply_workflow(doc, "Approve")
    finally:
        frappe.set_user("Administrator")
    return doc, approver


class TestMovementCostTransferAmount(FrappeTestCase):
    def test_a_zero_amount_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _transfer(amount=0).insert(ignore_permissions=True)

    def test_a_negative_amount_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            _transfer(amount=-10).insert(ignore_permissions=True)


class TestMovementCostTransferDistinctTargets(FrappeTestCase):
    def test_one_project_on_both_sides_is_refused(self):
        project = make_project("_T-MCT Project From")
        with self.assertRaisesRegex(frappe.ValidationError, "must be different"):
            _transfer(from_project=project, to_project=project).insert(ignore_permissions=True)

    def test_one_cost_center_on_both_sides_is_refused(self):
        centre = frappe.get_all("Cost Center", limit=1, pluck="name")[0]
        with self.assertRaisesRegex(frappe.ValidationError, "must be different"):
            _transfer(from_cost_center=centre, to_cost_center=centre).insert(
                ignore_permissions=True
            )

    def test_two_different_projects_are_accepted(self):
        doc = _transfer().insert(ignore_permissions=True)
        self.assertNotEqual(doc.from_project, doc.to_project)


class TestMovementCostTransferApprover(FrappeTestCase):
    def test_an_approved_transfer_stamps_the_approving_user(self):
        doc, approver = _approved()
        self.assertEqual(doc.approved_by, approver)

    def test_a_draft_transfer_names_no_approver(self):
        doc = _transfer().insert(ignore_permissions=True)
        self.assertFalse(doc.approved_by)

    def test_an_approver_already_named_is_kept(self):
        named = _user("_T-MCT Approver")
        doc, approver = _approved(approved_by=named)
        self.assertEqual(doc.approved_by, named)
        self.assertNotEqual(doc.approved_by, approver)

    def test_the_owner_cannot_approve_their_own_transfer(self):
        doc = _pending()
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Approve")


class TestMovementCostTransferCompany(FrappeTestCase):
    def test_a_transfer_with_no_company_is_filled_from_the_salis_default(self):
        doc = _transfer().insert(ignore_permissions=True)
        self.assertTrue(doc.company)
