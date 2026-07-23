# Copyright (c) 2026, AFMCO and contributors
"""Behavioural tests for the Movement Cost Recovery acknowledgement gate.

The recovery may not be *authorised* against a person until that person has
accepted responsibility (``acknowledgement_received``). The enforcement points
are the Approve transition (which submits the doc, docstatus 1) and Recover.
These tests drive the real ``frappe.model.workflow.apply_workflow`` so they
exercise the same path a desk action takes, and lock in the corrected gate:
the previous gate guarded ``Acknowledged``/``Recovered`` and left ``Approved``
(the actual submit) ungated, so a recovery could be approved against an
employee with no acknowledgement at all.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_workflow_name
from apex.tests._helpers import _user

# [#p0xvzg]
test_ignore = ["Mode of Payment", "Payment Entry", "Payment Gateway", "Salis Payment Request"]

WORKFLOW = "Movement Cost Recovery Workflow"


@unittest.skipUnless(
    get_workflow_name("Movement Cost Recovery") == WORKFLOW,
    "Movement Cost Recovery Workflow not seeded on this site",
)
class TestMovementCostRecoveryAck(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # [#4ui2y8]
        cls.manager = _user("mcr_mgr@example.com", "Fleet Manager")

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _recovery(self, acknowledged=False):
        """A draft Open recovery owned by Administrator, with the reqd fields filled
        so only the acknowledgement gate can block it."""
        return frappe.get_doc(
            {
                "doctype": "Movement Cost Recovery",
                "recovery_type": "Fuel Misuse",
                "amount": 500,
                "basis_evidence": "/files/qa-evidence.pdf",
                "acknowledgement_received": 1 if acknowledged else 0,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)

    def test_approve_blocked_without_acknowledgement(self):
        # [#1ytj1k]
        rec = self._recovery(acknowledged=False)
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rec, "Approve")
        rec.reload()
        self.assertEqual(rec.docstatus, 0)
        self.assertEqual(rec.status, "Open")

    def test_approve_allowed_with_acknowledgement(self):
        rec = self._recovery(acknowledged=True)
        frappe.set_user(self.manager)
        apply_workflow(rec, "Approve")
        rec.reload()
        self.assertEqual(rec.status, "Approved")
        self.assertEqual(rec.docstatus, 1)

    def test_recover_requires_acknowledgement(self):
        # [#2exq8g]
        rec = self._recovery(acknowledged=True)
        frappe.set_user(self.manager)
        apply_workflow(rec, "Approve")
        rec.reload()

        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Movement Cost Recovery", rec.name, "acknowledgement_received", 0
        )
        rec.reload()
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rec, "Recover")
        rec.reload()
        self.assertEqual(rec.status, "Approved")


@unittest.skipUnless(
    get_workflow_name("Movement Cost Recovery") == WORKFLOW,
    "Movement Cost Recovery Workflow not seeded on this site",
)
class TestMovementCostRecoverySelfApproval(FrappeTestCase):
    """The Approve transition is the money decision that gates the downstream
    Salis Payment Request against a driver's salary, so it must enforce
    segregation of duties: the creator/owner may not approve their own recovery.
    The DocType has no requested_by field, so allow_self_approval=0 (which gates
    on doc.owner) plus the explicit ``doc.owner != frappe.session.user`` condition
    are the only self-approval defenses. These tests pin both: the owner is
    refused Approve; a different Fleet Manager succeeds.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = _user("mcr_owner@example.com", "Fleet Manager")
        cls.other = _user("mcr_other@example.com", "Fleet Manager")

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _owned_recovery(self):
        """An Open recovery whose doc.owner is cls.owner (created while logged in
        as that manager), acknowledged so only the self-approval gate can block."""
        frappe.set_user(self.owner)
        rec = frappe.get_doc(
            {
                "doctype": "Movement Cost Recovery",
                "recovery_type": "Fuel Misuse",
                "amount": 500,
                "basis_evidence": "/files/qa-evidence.pdf",
                "acknowledgement_received": 1,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        frappe.set_user("Administrator")
        return rec

    def test_owner_cannot_approve_own_recovery(self):
        rec = self._owned_recovery()
        self.assertEqual(rec.owner, self.owner)
        frappe.set_user(self.owner)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rec, "Approve")
        rec.reload()
        self.assertEqual(rec.docstatus, 0)
        self.assertEqual(rec.status, "Open")

    def test_other_fleet_manager_can_approve(self):
        rec = self._owned_recovery()
        frappe.set_user(self.other)
        apply_workflow(rec, "Approve")
        rec.reload()
        self.assertEqual(rec.docstatus, 1)
        self.assertEqual(rec.status, "Approved")


@unittest.skipUnless(
    get_workflow_name("Movement Cost Recovery") == WORKFLOW,
    "Movement Cost Recovery Workflow not seeded on this site",
)
class TestMovementCostRecoveryDoA(FrappeTestCase):
    """Delegation-of-Authority tier gate: a recovery at/above the Cost Recovery
    Operations Threshold needs Operations-tier authority (Fleet Manager); below it
    Regional-tier (Fleet Supervisor) suffices. Proves the threshold is REAL (was
    previously a dead Salis Settings field with no reader)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = _user("mcr_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("mcr_doa_mgr@example.com", "Fleet Manager")

    def setUp(self):
        frappe.set_user("Administrator")
        # [#4t35wf]
        self.settings = frappe.get_single("Salis Settings")
        self.settings.cost_recovery_ops_threshold = 1000
        self.settings.save(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")

    def _recovery(self, amount):
        return frappe.get_doc(
            {
                "doctype": "Movement Cost Recovery",
                "recovery_type": "Fuel Misuse",
                "amount": amount,
                "basis_evidence": "/files/qa-evidence.pdf",
                "acknowledgement_received": 1,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)

    def test_needs_operations_derived_from_amount(self):
        below = self._recovery(amount=999)
        self.assertEqual(below.needs_operations, 0)
        at = self._recovery(amount=1000)
        self.assertEqual(at.needs_operations, 1)
        above = self._recovery(amount=5000)
        self.assertEqual(above.needs_operations, 1)

    def test_gate_fires_above_threshold_for_regional_user(self):
        # [#trvxci]
        rec = self._recovery(amount=5000)
        frappe.set_user(self.supervisor)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rec, "Authorize (Regional)")
        rec.reload()
        self.assertEqual(rec.docstatus, 0)
        self.assertEqual(rec.status, "Open")

    def test_gate_passes_below_threshold_for_regional_user(self):
        # [#6rrf29]
        rec = self._recovery(amount=500)
        frappe.set_user(self.supervisor)
        apply_workflow(rec, "Authorize (Regional)")
        rec.reload()
        self.assertEqual(rec.docstatus, 1)
        self.assertEqual(rec.status, "Approved")

    def test_operations_user_passes_above_threshold(self):
        # [#gs0ao5]
        rec = self._recovery(amount=5000)
        frappe.set_user(self.manager)
        apply_workflow(rec, "Approve")
        rec.reload()
        self.assertEqual(rec.docstatus, 1)
        self.assertEqual(rec.status, "Approved")
