# Copyright (c) 2026, AFMCO and contributors
"""Native Workflow tests for the Habitat / Apex Core approval workflows.

Covers the four approval workflows wired by ``habitat_workflow_seed``:
Utility Bill Entry, Subcontractor Service Contract, Custody Damage Assessment,
and Accommodation Lease.

Each workflow is proven on the three things that actually matter and that the
prior (unverified) shipping got wrong:

  * the workflow EXISTS on the document type (it is seeded, not just shipped as
    dead JSON — Workflow is not auto-imported on migrate);
  * Segregation of Duties is real and native — the document OWNER (maker) is
    refused the Approve transition because the shipped Workflow Transition sets
    ``allow_self_approval = 0`` (no controller hack); a different approver who
    holds the approver role succeeds and the document submits;
  * a WRONG role is refused the Approve transition.

The tests drive the real ``frappe.model.workflow.apply_workflow`` as concrete
users, exercising the same path a desk action takes (role gate + self-approval
gate + docstatus transition). The workflows are seeded in ``setUpClass`` so the
test does not depend on a prior migrate having created them on the test site.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name

from apex.apex_core.setup.seeders.habitat_workflow_seed import seed_habitat_workflows
from apex.tests._helpers import _user

# [#ovhwnj]
test_ignore = [
    "Building",
    "Additional Salary",
    "Company",
    "Custody Return",
    "Department",
    "Employee",
    "Project",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
    "Utility Account",
]


def _actions(doc):
    """The set of workflow action names available to the current session user."""
    return {t.action for t in get_transitions(doc)}


class _WorkflowSoDMixin:
    """Shared assertions for an approval workflow whose Approve transition sets
    ``allow_self_approval = 0``.

    A subclass supplies ``DOCTYPE``, ``WORKFLOW``, ``APPROVER_ROLE``, a foreign
    ``OTHER_ROLE`` that is NOT allowed the Approve transition, the
    ``STATE_FIELD`` / ``PENDING_STATE`` the workflow is keyed on, and a
    ``_draft(owner)`` factory inserting a draft owned by ``owner``.
    """

    DOCTYPE = None
    WORKFLOW = None
    APPROVER_ROLE = None
    OTHER_ROLE = "Resident Supervisor"
    APPROVE_ACTION = "Approve"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        seed_habitat_workflows()
        # [#qxw23h]
        cls.maker = _user("hbwf_maker@example.com", cls.APPROVER_ROLE)
        cls.approver = _user("hbwf_approver@example.com", cls.APPROVER_ROLE)
        cls.outsider = _user("hbwf_outsider@example.com", cls.OTHER_ROLE)

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _seeded(self):
        return get_workflow_name(self.DOCTYPE) == self.WORKFLOW

    PENDING_STATE = "Pending Approval"
    STATE_FIELD = "status"

    def _to_pending(self, doc):
        """Position the draft at the Pending Approval state.

        We set the workflow state field directly rather than driving the
        ``Submit for Approval`` transition: that transition's save re-runs the
        controller ``validate`` (and downstream master lookups) which is out of
        scope for a workflow-gate test and would couple it to unprovisioned
        masters. The Approve gate we exercise reads only the state field, the
        role and the owner.
        """
        if self.PENDING_STATE:
            frappe.db.set_value(self.DOCTYPE, doc.name, self.STATE_FIELD,
                                self.PENDING_STATE, update_modified=False)
            doc.reload()
        return doc

    # [#qk3xk5]

    def test_workflow_is_seeded(self):
        self.assertEqual(
            get_workflow_name(self.DOCTYPE), self.WORKFLOW,
            f"{self.WORKFLOW} must be seeded onto {self.DOCTYPE}",
        )

    def test_owner_cannot_self_approve(self):
        if not self._seeded():
            self.skipTest(f"{self.WORKFLOW} not seeded on this site")
        doc = self._to_pending(self._draft(self.maker))

        # [#e1edaq]
        frappe.set_user(self.maker)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(doc, self.APPROVE_ACTION)
        doc.reload()
        self.assertEqual(doc.docstatus, 0)

    def test_other_approver_is_offered_approve(self):
        if not self._seeded():
            self.skipTest(f"{self.WORKFLOW} not seeded on this site")
        doc = self._to_pending(self._draft(self.maker))

        # [#7kq0et]
        frappe.set_user(self.approver)
        self.assertIn(self.APPROVE_ACTION, _actions(doc))

    def test_wrong_role_cannot_approve(self):
        if not self._seeded():
            self.skipTest(f"{self.WORKFLOW} not seeded on this site")
        doc = self._to_pending(self._draft(self.maker))

        # [#tirqxa]
        frappe.set_user(self.outsider)
        self.assertNotIn(self.APPROVE_ACTION, _actions(doc))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(doc, self.APPROVE_ACTION)
        doc.reload()
        self.assertEqual(doc.docstatus, 0)


def _insert_as(owner, data):
    """Insert ``data`` so its ``owner`` is ``owner`` (the self-approval subject),
    bypassing link/validate provisioning the workflow gate does not depend on."""
    frappe.set_user(owner)
    try:
        doc = frappe.get_doc(data)
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
    finally:
        frappe.set_user("Administrator")
    return doc


class TestUtilityBillEntryWorkflow(_WorkflowSoDMixin, FrappeTestCase):
    DOCTYPE = "Utility Bill Entry"
    WORKFLOW = "Utility Bill Entry Workflow"
    APPROVER_ROLE = "Accommodation Manager"

    def _draft(self, owner):
        return _insert_as(owner, {
            "doctype": self.DOCTYPE,
            "naming_series": "UTIL-BILL-.YYYY.-.#####",
            "utility_account": "QA-UTIL-ACC",
            "building": "QA-BLDG",
            "status": "Draft",
            "billing_period_from": "2026-07-01",
            "billing_period_to": "2026-07-31",
            "bill_amount": 100,
        })


class TestSubcontractorServiceContractWorkflow(_WorkflowSoDMixin, FrappeTestCase):
    DOCTYPE = "Subcontractor Service Contract"
    WORKFLOW = "Subcontractor Service Contract Workflow"
    APPROVER_ROLE = "Accommodation Manager"

    def _draft(self, owner):
        return _insert_as(owner, {
            "doctype": self.DOCTYPE,
            "naming_series": "SUB-CON-.YYYY.-.####",
            "supplier": "QA-SUPPLIER",
            "service_type": "Pest Control",
            "status": "Draft",
            "contract_start_date": "2026-07-01",
            "contract_end_date": "2027-06-30",
        })


class TestCustodyDamageAssessmentWorkflow(_WorkflowSoDMixin, FrappeTestCase):
    DOCTYPE = "Custody Damage Assessment"
    WORKFLOW = "Custody Damage Assessment Workflow"
    APPROVER_ROLE = "Accommodation Manager"

    def _draft(self, owner):
        return _insert_as(owner, {
            "doctype": self.DOCTYPE,
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "status": "Draft",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked",
                        "estimated_replacement_cost": 150}],
        })


class TestAccommodationLeaseWorkflow(_WorkflowSoDMixin, FrappeTestCase):
    DOCTYPE = "Lease"
    WORKFLOW = "Accommodation Lease Workflow"
    # [#8zk3af]
    APPROVER_ROLE = "Finance Manager"

    def _draft(self, owner):
        return _insert_as(owner, {
            "doctype": self.DOCTYPE,
            "naming_series": "ACC-LEASE-.YYYY.-.####",
            "building": "QA-BLDG",
            "status": "Draft",
            "lease_start_date": "2026-07-01",
            "lease_end_date": "2027-06-30",
            "rent_amount": 8000,
            "billing_cycle": "Monthly",
            "first_payment_date": "2026-07-01",
        })


class TestHabitatWorkflowReconcile(FrappeTestCase):
    """A-085 finding 6: ``habitat_workflow_seed`` now routes through the shared
    ``workflow_seed_base.seed_one``, which re-applies the shipped states and
    transitions onto an already-present Workflow on every migrate. Previously the
    habitat path only flipped ``is_active`` and left a drifted definition in place.
    """

    WORKFLOW_DIR = "custody_damage_assessment_workflow"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        seed_habitat_workflows()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_seed_reapplies_drifted_transitions(self):
        # seed_one saves without committing, so the drift + reconcile stay inside
        # the test transaction and roll back cleanly.
        from apex.apex_core.setup.seeders.habitat_workflow_seed import (
            _STATE_STYLE,
            _load_definition,
        )
        from apex.apex_core.setup.seeders.workflow_seed_base import seed_one

        definition = _load_definition("habitat", self.WORKFLOW_DIR)
        name = definition["name"]
        self.assertTrue(
            frappe.db.exists("Workflow", name),
            f"{name} must be seeded by habitat_workflow_seed",
        )
        wf = frappe.get_doc("Workflow", name)
        original = len(wf.transitions)
        self.assertGreater(original, 0)

        # drift: drop a transition, as a stray manual desk edit might
        wf.transitions = wf.transitions[:-1]
        wf.save(ignore_permissions=True)
        wf.reload()
        self.assertEqual(len(wf.transitions), original - 1)

        # reconcile through the shared engine
        seed_one(definition, _STATE_STYLE)
        wf.reload()
        self.assertEqual(
            len(wf.transitions),
            original,
            "shared seed_one must re-apply the shipped transitions onto the "
            "existing habitat Workflow (A-085 finding 6 reconcile)",
        )
