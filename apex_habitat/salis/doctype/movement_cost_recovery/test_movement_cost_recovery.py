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

from apex_habitat.tests._helpers import _user

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
        # The approver must differ from the owner (Approve has allow_self_approval=0).
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
        # The Open -> Approve transition submits the doc (docstatus 1); the gate must
        # fire here -- this is the path the buggy gate left unguarded.
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
        # Reaching Recovered also enforces the gate. Guard the value directly: an
        # already-Approved (submitted) recovery whose flag is cleared cannot be moved
        # to Recovered.
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
