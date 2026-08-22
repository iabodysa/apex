# Copyright (c) 2026, afmcoltd
"""What Custody Damage Assessment guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is the module-level
``validate`` wired in ``hooks.py``, moved through its real Workflow
(``Custody Damage Assessment Workflow``: Draft -[Submit for Approval]-> Pending Approval
-[Approve]-> Approved, or -[Reject]-> Rejected -[Revise]-> Draft) via
``frappe.model.workflow.apply_workflow`` rather than a raw status assignment, because the
workflow is the real door a user pushes the record through. ``validate`` totals the
assessment from its ``items`` table (there is no payroll posting on this path; recovery
runs through HRMS Employee Advance elsewhere), stamps ``assessed_by`` the moment the
record leaves Draft and drops it the moment ``Revise`` returns it there, stamps
``approved_by``/``approved_on`` at Approved, and derives ``acknowledged_on`` from the
worker's signature, dropping it the moment the signature is removed.
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Custody Article"]


def _apply(record, action):
    """Push the record through one real workflow transition and return the reloaded doc."""
    apply_workflow({"doctype": record.doctype, "name": record.name}, action)
    return frappe.get_doc(record.doctype, record.name)


class TestCustodyDamageAssessment(FrappeTestCase):
    def test_the_total_is_the_sum_of_the_item_replacement_costs(self):
        """A replacement-cost notice must total what its own item rows say, nothing else."""
        second_article = frappe.db.get_value(
            "Custody Article", {"article_name": "_Test Pillow"}, "name"
        )
        record = frappe.copy_doc(frappe.get_test_records("Custody Damage Assessment")[0])
        record.append(
            "items",
            {
                "article": second_article,
                "damage_description": "Second item",
                "estimated_replacement_cost": 30,
            },
        )
        record.insert()

        self.assertEqual(record.total_estimated_replacement_cost, 80)

    def test_assessed_by_is_stamped_on_leaving_draft_and_cleared_on_returning_to_it(self):
        """A notice naming nobody as its assessor, or one that keeps naming one after
        reverting to Draft, cannot be defended."""
        record = frappe.copy_doc(frappe.get_test_records("Custody Damage Assessment")[0])
        record.insert()
        self.assertIsNone(record.assessed_by, "a Draft assessment must name no assessor")

        record = _apply(record, "Submit for Approval")
        self.assertEqual(record.status, "Pending Approval")
        self.assertEqual(record.assessed_by, frappe.session.user)

        record = _apply(record, "Reject")
        record = _apply(record, "Revise")
        self.assertEqual(record.status, "Draft")
        self.assertIsNone(
            record.assessed_by, "returning to Draft must drop the assessor it stamped"
        )

    def test_approved_by_and_approved_on_are_stamped_at_approved(self):
        """An approval notice must name who approved it and when, or it proves nothing."""
        record = frappe.copy_doc(frappe.get_test_records("Custody Damage Assessment")[0])
        record.insert()

        record = _apply(record, "Submit for Approval")
        record = _apply(record, "Approve")

        self.assertEqual(record.status, "Approved")
        self.assertEqual(record.docstatus, 1, "Approved is the workflow's submitted state")
        self.assertEqual(record.approved_by, frappe.session.user)
        self.assertIsNotNone(record.approved_on)

    def test_acknowledged_on_is_derived_from_the_signature_and_dropped_with_it(self):
        """A served-on date is proof the notice was served, and must not outlive the signature."""
        record = frappe.copy_doc(frappe.get_test_records("Custody Damage Assessment")[0])
        record.insert()
        self.assertIsNone(record.acknowledged_on)

        record.worker_signature = "data:image/png;base64,AAAA"
        record.save()
        self.assertIsNotNone(record.acknowledged_on)

        record.worker_signature = None
        record.save()
        self.assertIsNone(
            record.acknowledged_on,
            "removing the signature must drop the acknowledgement it evidenced",
        )
