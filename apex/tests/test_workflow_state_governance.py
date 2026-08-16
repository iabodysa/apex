# Copyright (c) 2026, AFMCO and contributors
"""The workflow-state field of every approval / lifecycle
DocType is ``read_only``, so the state is driven only by its native Workflow (or
the server engine) and can never be hand-edited on the form. Utility Bill Entry is
additionally pinned down to the four states its approval workflow actually uses
(the dead Received / Under Review / Paid / Disputed options were dropped).

Asserted against ``frappe.get_meta`` (the migrated DocType), not the on-disk
JSON, so it proves the field reached the database read_only.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

# DocType -> workflow-state field. Each is Workflow- or engine-driven, so its
# state field must be read_only.
STATE_FIELDS = {
    "Utility Bill Entry": "status",
    "Lease": "status",
    "Subcontractor Service Contract": "status",
    "Custody Damage Assessment": "status",
    "Dispatch Trip": "status",
    "Fuel Claim": "status",
    "Movement Cost Recovery": "status",
    "Movement Cost Transfer": "status",
    "Fuel Exception Case": "status",
    "Vehicle Damage Write-Off": "status",
    "Fuel Request": "status",
}

# An action that REFUSES. ``Cancel`` is abandonment and grades nothing; Fuel Claim and
# Rental Settlement refuse through Dispute rather than Reject, so a set that watches
# Reject alone grades both of them wrongly.
REFUSING_ACTIONS = {"Reject", "Dispute", "Block", "Return", "Revise", "Reopen"}


class TestWorkflowStateGovernance(FrappeTestCase):
    def test_state_fields_are_read_only(self):
        offenders = []
        checked = 0
        for doctype, fieldname in STATE_FIELDS.items():
            if not frappe.db.exists("DocType", doctype):
                continue
            checked += 1
            df = frappe.get_meta(doctype).get_field(fieldname)
            self.assertIsNotNone(df, f"{doctype}.{fieldname} field is missing")
            if not df.read_only:
                offenders.append(f"{doctype}.{fieldname}")
        self.assertEqual(
            offenders,
            [],
            "workflow-state fields must be read_only, or a user can type a state the "
            "workflow never granted: " + ", ".join(offenders),
        )
        # guard against the enumeration silently going empty (vacuous pass)
        self.assertGreaterEqual(checked, 10, "expected >=10 state fields, enumeration looks empty")

    def test_utility_bill_entry_status_options_trimmed(self):
        df = frappe.get_meta("Utility Bill Entry").get_field("status")
        options = [o for o in (df.options or "").split("\n") if o]
        self.assertEqual(
            options,
            ["Draft", "Pending Approval", "Approved", "Rejected"],
            "Utility Bill Entry.status must expose only the four approval states "
            "(the dead Received/Under Review/Paid/Disputed options were dropped)",
        )

    def test_only_dispatch_trip_carries_no_refusing_transition(self):
        """Every shipped Workflow refuses somewhere, except the one graded a record.

        The grade and its reason are written in
        ``apex/apex_core/setup/workflow_names.py``. This pins the population so a
        Workflow that quietly loses its last refusal cannot keep the approval
        machinery it no longer earns.
        """
        decisionless = []
        checked = 0
        for name in frappe.get_all(
            "Workflow", filters={"is_active": 1}, pluck="name"
        ):
            actions = {
                row.action for row in frappe.get_doc("Workflow", name).transitions
            }
            checked += 1
            if not (actions & REFUSING_ACTIONS):
                decisionless.append(name)
        self.assertGreaterEqual(
            checked, 16, "expected >=16 active Workflows, the enumeration looks empty"
        )
        self.assertEqual(
            sorted(decisionless),
            ["Dispatch Trip Workflow"],
            "a Workflow with no refusing transition encodes facts, not a decision; "
            "grade it in workflow_names.py before it ships",
        )

    def test_the_supervisor_who_dispatches_a_trip_can_complete_it(self):
        """Fleet Supervisor holds both halves of the forward act, or the board never clears.

        ``Completed`` is ``doc_status 1``, so the transition alone is not enough —
        ``apply_workflow`` calls ``submit()``, which checks the submit DocPerm.
        """
        transitions = frappe.get_doc("Workflow", "Dispatch Trip Workflow").transitions
        dispatchers = {t.allowed for t in transitions if t.action == "Dispatch"}
        completers = {t.allowed for t in transitions if t.action == "Complete"}
        self.assertTrue(dispatchers, "Dispatch Trip Workflow lost its Dispatch action")
        self.assertLessEqual(
            dispatchers,
            completers,
            "every role that can dispatch a trip must be able to complete it, or a "
            "finished trip stays on the supervisor's active board",
        )
        submitters = {
            row.role
            for row in frappe.get_meta("Dispatch Trip").permissions
            if row.submit and not row.permlevel
        }
        self.assertTrue(
            completers <= submitters,
            "a role allowed to Complete a trip needs submit on Dispatch Trip, because "
            f"Completed is doc_status 1: {sorted(completers - submitters)} lack it",
        )
