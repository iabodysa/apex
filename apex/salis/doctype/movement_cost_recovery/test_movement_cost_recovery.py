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

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_workflow_name
from apex.tests._helpers import _grant_project, _user
from apex.tests.factories import make_project, make_vehicle
from frappe.model.workflow import apply_workflow, get_transitions


WORKFLOW = "Movement Cost Recovery Workflow"


def setUpModule():
    """this is a MANDATORY Salis workflow, seeded by salis_workflow_seed on every
    install and migrate. Its absence is a regression — FAIL, never skip.

    None of the three classes below may carry ``@unittest.skipUnless(get_workflow_name(...))``:
    that decorator evaluates at IMPORT time, so it would turn the seed regression this
    file exists to catch into a silent green run of nine cases instead of the FAIL above.
    The two sibling workflow suites in this tree (fuel_claim, fuel_exception_case) apply
    the same ``setUpModule`` convention.
    """
    active = get_workflow_name("Movement Cost Recovery")
    if active != WORKFLOW:
        raise AssertionError(
            f"Mandatory Salis workflow {WORKFLOW!r} not active for "
            f"'Movement Cost Recovery' (got {active!r}) — salis_workflow_seed regression"
        )


class TestMovementCostRecoveryAck(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
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


class TestMovementCostRecoveryDoA(FrappeTestCase):
    """Delegation-of-Authority tier gate: a recovery at/above the Cost Recovery
    Operations Threshold needs Operations-tier authority (Fleet Manager); below it
    Regional-tier (Fleet Supervisor) suffices. Proves the threshold is REAL: the
    DoA tier gate has a reader for the Salis Settings field and actually branches
    on it, rather than the field sitting unread.

    Movement Cost Recovery is project-scoped through its vehicle (``SALIS_SCOPE``
    maps it to a hop onto ``Salis Vehicle.project``), and Fleet Supervisor is a
    SCOPED role while Fleet Manager is one of the unscoped oversight roles. A
    recovery carrying no vehicle therefore anchors to no project and the document
    check fails closed for the supervisor — before the DoA gate is ever consulted,
    and with a PermissionError that ``assertRaises(ValidationError)`` would happily
    swallow, since PermissionError subclasses it. Every recovery here is anchored to
    a vehicle in a project the supervisor is permitted for, so the tier gate is what
    each case actually measures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.supervisor = _user("mcr_sup@example.com", "Fleet Supervisor")
        cls.manager = _user("mcr_doa_mgr@example.com", "Fleet Manager")
        cls.project = make_project("MCR DoA Project")
        _grant_project(cls.supervisor, cls.project)
        cls.vehicle = make_vehicle("MCR DOA 1", project=cls.project)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "User Permission",
            {"allow": "Project", "for_value": cls.project, "user": cls.supervisor},
        )
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")
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
                "vehicle": self.vehicle,
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
        rec = self._recovery(amount=5000)
        frappe.set_user(self.supervisor)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(rec, "Authorize (Regional)")
        rec.reload()
        self.assertEqual(rec.docstatus, 0)
        self.assertEqual(rec.status, "Open")

    def test_gate_passes_below_threshold_for_regional_user(self):
        rec = self._recovery(amount=500)
        frappe.set_user(self.supervisor)
        apply_workflow(rec, "Authorize (Regional)")
        rec.reload()
        self.assertEqual(rec.docstatus, 1)
        self.assertEqual(rec.status, "Approved")

    def test_operations_user_passes_above_threshold(self):
        rec = self._recovery(amount=5000)
        frappe.set_user(self.manager)
        apply_workflow(rec, "Approve")
        rec.reload()
        self.assertEqual(rec.docstatus, 1)
        self.assertEqual(rec.status, "Approved")

test_ignore = ['Mode of Payment', 'Payment Entry', 'Payment Gateway', 'Salis Payment Request']


# --- merged from test_rejected_has_a_way_out.py ---
WORKFLOW_rejected_has_a_way_out = "Movement Cost Recovery Workflow"
MANAGER_ROLE = "Fleet Manager"
def _h(n=12):
    return frappe.generate_hash(length=n).upper()
class TestARejectedRecoveryCanStillBeResolved(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.manager = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"mcr-{_h()}@example.com".lower(),
                "first_name": "Fleet Manager Fixture",
                "send_welcome_email": 0,
                "roles": [{"role": MANAGER_ROLE}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", cls.manager.name, force=True, ignore_permissions=True
        )
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _rejected_recovery(self):
        doc = frappe.get_doc(
            {
                "doctype": "Movement Cost Recovery",
                "recovery_type": "Other",
                "amount": 25,
                "basis_evidence": "/files/mcr-fixture.pdf",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(self._drop, doc.name)
        frappe.set_user(self.manager.name)
        apply_workflow(doc, "Reject")
        self.assertEqual(doc.status, "Rejected")
        self.assertEqual(doc.docstatus, 1, "rejecting is expected to submit the record")
        return doc

    def _drop(self, name):
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Movement Cost Recovery", name, "docstatus", 0, update_modified=False
        )
        frappe.delete_doc(
            "Movement Cost Recovery", name, force=True, ignore_permissions=True
        )

    def test_the_rejecting_manager_is_offered_a_way_out(self):
        """The desk draws its workflow buttons from get_transitions, so an empty list is
        a document with no action on screen."""
        doc = self._rejected_recovery()
        actions = [t.action for t in get_transitions(doc)]
        self.assertTrue(
            actions,
            "a rejected recovery offered the manager who rejected it no action at all",
        )

    def test_the_way_out_reaches_a_terminal_state(self):
        """An offered button is only an answer if pressing it resolves the document."""
        doc = self._rejected_recovery()
        apply_workflow(doc, "Cancel")
        doc.reload()
        self.assertEqual(doc.status, "Cancelled")
        self.assertEqual(doc.docstatus, 2)

    def test_no_state_in_this_workflow_strands_a_submitted_document(self):
        """The sweep the card asks for, held as a test so it cannot regress. A submitted
        state with no outgoing transition is legitimate when it is an END — the recovery
        was collected, waived, or voided. A refusal is not an end, and Rejected was the
        only refusal state in the app that had no way out."""
        workflow = frappe.get_doc("Workflow", WORKFLOW_rejected_has_a_way_out)
        leaves = {t.state for t in workflow.transitions}
        stranded = sorted(
            s.state
            for s in workflow.states
            if str(s.doc_status) == "1" and s.state not in leaves
        )
        self.assertEqual(
            stranded,
            ["Recovered", "Waived"],
            "the submitted states with no way out must be the two that mean the recovery is over",
        )
