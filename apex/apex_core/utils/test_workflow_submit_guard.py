# Copyright (c) 2026, AFMCO and contributors
"""Guard tests for the native-submit / native-cancel workflow bypass (A-083).

The guard (``apex.apex_core.utils.workflow_guard``) re-validates authorization on a
bare ``doc.submit()`` / ``frappe.client.submit`` (or ``doc.cancel()``) of a
workflow-governed doctype, replicating ``apply_workflow``'s gate: it allows the submit
only when the current user holds an authorized transition from the current state to a
submit (doc_status 1) state — role + condition via ``get_transitions``, self-approval via
``has_approval_access``. It blocks the force-jump bypass without breaking a legitimately
authorized submit.

Three properties are proven:

NEGATIVE - force-jump blocked. A bare submit that would jump straight to docstatus 1 from
a state with NO authorized transition to a submit state is refused, and the document stays
at docstatus 0. Issued as **Administrator** (all roles, always passes ``has_approval_access``
and holds native submit-permission) from such a state, so the ONLY thing that can refuse it
is the guard's force-jump check - proven even for the most privileged user. Covers Salis
Payment Request (Draft), Driver Clearance (Blocked) and Custody Damage Assessment (Draft).

NEGATIVE - self-approval blocked. A Custody Damage Assessment sitting in Pending Approval,
whose Approve transition sets ``allow_self_approval = 0``, is bare-submitted by its OWNER
(an Accommodation Manager who does hold native submit-permission and the approver role, so
only the guard can refuse it). ``get_transitions`` alone WOULD offer Approve here - the
guard additionally applies ``has_approval_access``, which is exactly what refuses the owner.
Document stays at docstatus 0.

POSITIVE - authorized approver still submits. The real ``apply_workflow`` approval path
drives Salis Payment Request and Driver Clearance to docstatus 1, and on the same
Pending-Approval Custody Damage Assessment a DIFFERENT Accommodation Manager passes the
guard (the self-approval refusal is about identity, not the role). The full per-workflow
suites (``test_*_workflow.py``) are the broader no-regression proof.
"""

import frappe
from frappe.client import submit as client_submit
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.workflow_guard import before_submit as guard_before_submit
from apex.tests._helpers import _user
from apex.tests.factories import make_project


class TestWorkflowSubmitGuard(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # The workflows this guard runs against arrive with the app: they are fixtures,
        # imported on install and on every migrate.

        cls.maker = _user("wfg_maker@example.com", "Fleet Project Manager")
        cls.finance = _user("wfg_fin@example.com", "Finance Manager")
        cls.fleet_mgr = _user("wfg_fleetmgr@example.com", "Fleet Manager")
        # Two distinct Accommodation Managers: the maker/owner (refused self-approval)
        # and a foreign approver (accepted).
        cls.am_maker = _user("wfg_am_maker@example.com", "Accommodation Manager")
        cls.am_approver = _user("wfg_am_approver@example.com", "Accommodation Manager")

        cls.project = make_project("WFG Guard Project")
        cls._grant_project(cls.maker, cls.project)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "User Permission",
            {"allow": "Project", "for_value": cls.project, "user": cls.maker},
        )
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    # Fixtures

    @staticmethod
    def _grant_project(user, project):
        if not frappe.db.exists(
            "User Permission", {"allow": "Project", "for_value": project, "user": user}
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "allow": "Project",
                    "for_value": project,
                    "user": user,
                }
            ).insert(ignore_permissions=True)

    def _payment_request(self):
        return frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Fuel",
                "amount": 250,
                "requested_by": self.maker,
                "project": self.project,
                "status": "Draft",
            }
        ).insert(ignore_permissions=True)

    def _driver(self, name):
        d = frappe.db.get_value("Salis Driver", {"full_name": name}, "name")
        if not d:
            d = frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": name,
                    "status": "Active",
                    "project": self.project,
                }
            ).insert(ignore_permissions=True).name
        return d

    def _driver_clearance(self, driver):
        return frappe.get_doc(
            {
                "doctype": "Driver Clearance",
                "driver": driver,
                "clearance_reason": "End of Assignment",
                "vehicle_returned": 1,
                "fuel_chip_returned": 1,
                "custody_returned": 1,
                "status": "Open",
            }
        ).insert(ignore_permissions=True)

    def _damage_assessment(self, owner=None):
        """A minimal Custody Damage Assessment. Master links are out of scope for a
        workflow-gate test (the guard fires before docstatus is persisted), so insert
        with ``ignore_links`` / ``ignore_mandatory``. When ``owner`` is given, insert as
        that user so it is the self-approval subject."""
        data = {
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-WFG-BLDG",
            "status": "Draft",
            "items": [
                {
                    "doctype": "Custody Damage Item",
                    "article": "QA-WFG-ART",
                    "damage_description": "cracked",
                    "estimated_replacement_cost": 150,
                }
            ],
        }
        if owner:
            frappe.set_user(owner)
        try:
            doc = frappe.get_doc(data)
            doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        finally:
            frappe.set_user("Administrator")
        return doc

    @staticmethod
    def _park(doc, state):
        """Land the workflow state field on ``state`` via a raw db write (no submit, no
        transition), so the guard reads that state as the current one."""
        frappe.db.set_value(doc.doctype, doc.name, "status", state, update_modified=False)
        doc.reload()
        return doc

    def _assert_bare_submit_blocked(self, doctype, name):
        """A fresh-loaded doc, bare-submitted as Administrator, is refused by the guard
        and its PERSISTED docstatus stays 0."""
        doc = frappe.get_doc(doctype, name)
        # Skip link validation so the guard (not a LinkValidationError) is the blocker.
        doc.flags.ignore_links = True
        with self.assertRaises(frappe.PermissionError):
            doc.submit()
        self.assertEqual(frappe.db.get_value(doctype, name, "docstatus"), 0)

    # NEGATIVE: force-jump bypass blocked

    def test_bare_submit_salis_payment_request_blocked(self):
        # Draft has no authorized transition to a submit state (Draft -> Pending Finance
        # only), so the force-jump is refused even for Administrator.
        pr = self._payment_request()
        self._assert_bare_submit_blocked("Salis Payment Request", pr.name)
        self.assertEqual(
            frappe.db.get_value("Salis Payment Request", pr.name, "status"), "Draft"
        )

    def test_client_submit_salis_payment_request_blocked(self):
        pr = self._payment_request()
        # The desk "Submit" action routes here; it too must not force docstatus 1.
        with self.assertRaises(frappe.PermissionError):
            client_submit(frappe.as_json(pr.as_dict()))
        self.assertEqual(
            frappe.db.get_value("Salis Payment Request", pr.name, "docstatus"), 0
        )

    def test_bare_submit_driver_clearance_blocked(self):
        # From Blocked the only transition is Reopen -> In Progress (doc_status 0); there
        # is no authorized transition to Cleared, so the force-jump is refused. (From Open
        # a Fleet Manager IS authorized to Clear, so Open would legitimately pass - which
        # is why the negative is asserted from a non-approving state.)
        dc = self._driver_clearance(self._driver("WFG Guard Driver"))
        self._park(dc, "Blocked")
        self._assert_bare_submit_blocked("Driver Clearance", dc.name)
        self.assertEqual(
            frappe.db.get_value("Driver Clearance", dc.name, "status"), "Blocked"
        )

    def test_bare_submit_custody_damage_assessment_blocked(self):
        # Draft -> Pending Approval only; no authorized transition to Approved from Draft.
        cda = self._damage_assessment()
        self._assert_bare_submit_blocked("Custody Damage Assessment", cda.name)

    # NEGATIVE: self-approval blocked (has_approval_access)

    def test_owner_self_approval_custody_damage_assessment_blocked(self):
        """The Approve transition (Pending Approval -> Approved) sets
        ``allow_self_approval = 0``. ``get_transitions`` still offers it to the owner (role
        matches, no condition); the guard additionally applies ``has_approval_access``,
        which refuses the owner. Proven as the OWNER (an Accommodation Manager who holds
        native submit-permission), so only the guard can be the blocker."""
        cda = self._damage_assessment(owner=self.am_maker)
        self._park(cda, "Pending Approval")

        frappe.set_user(self.am_maker)
        cda.flags.ignore_links = True
        with self.assertRaises(frappe.PermissionError):
            cda.submit()
        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value("Custody Damage Assessment", cda.name, "docstatus"), 0
        )

    # POSITIVE: authorized approver still submits

    def test_apply_workflow_salis_payment_request_submits(self):
        pr = self._payment_request()
        frappe.set_user(self.maker)
        apply_workflow(pr, "Submit to Finance")
        frappe.set_user(self.finance)
        apply_workflow(pr, "Approve (Finance)")
        frappe.set_user("Administrator")
        pr.reload()
        self.assertEqual(pr.status, "Approved by Finance")
        self.assertEqual(pr.docstatus, 1)

    def test_apply_workflow_driver_clearance_submits(self):
        dc = self._driver_clearance(self._driver("WFG Guard Driver Clear"))
        frappe.set_user(self.fleet_mgr)
        apply_workflow(dc, "Clear")
        frappe.set_user("Administrator")
        dc.reload()
        self.assertEqual(dc.status, "Cleared")
        self.assertEqual(dc.docstatus, 1)

    def test_authorized_approver_passes_guard_custody_damage_assessment(self):
        """On the same Pending-Approval assessment that refuses its owner, a DIFFERENT
        Accommodation Manager passes the guard: ``has_approval_access`` is True for a
        non-owner, so the guard admits the authorized approver (the refusal is about
        identity, not the role)."""
        cda = self._damage_assessment(owner=self.am_maker)
        self._park(cda, "Pending Approval")

        frappe.set_user(self.am_approver)
        try:
            # The guard must NOT raise for the authorized (non-owner) approver.
            guard_before_submit(cda)
        finally:
            frappe.set_user("Administrator")
