# Copyright (c) 2026, afmcoltd
"""What a Safety Task Execution guarantees, asserted against the DocType itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_validate`` / ``test_update_after_submit``).

Three guarantees: (1) ``validate`` refuses a FAILED outcome (Poor / Not Done) on a
Safety Task Catalog task flagged ``evidence_required`` unless an Evidence Photo is
attached, and separately refuses a Security-category actionable finding without one;
(2) ``on_submit`` raises exactly one building-scoped Maintenance Request for a failed
execution, stamping ``linked_maintenance_request`` (idempotent — never for a passing
result); (3) ``on_cancel`` closes that ticket, but only while it is still an untouched
Draft at status Open.

``Room`` is not a link field on this DocType (``_scope_room`` reads the Room table
directly), so it is declared in ``test_dependencies`` explicitly rather than relying on
the framework's own link-field dependency scan.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Room"]


def _make_catalog_task(*, evidence_required=0, department="Fire Safety"):
    """A fresh Safety Task Catalog entry with a controlled evidence_required / department,
    independent of the shared test_records.json fixture (whose flags this test cannot rely
    on)."""
    catalog = frappe.new_doc("Safety Task Catalog")
    catalog.task_title = "_Test Escalation Task"
    catalog.task_code = frappe.generate_hash(length=8)
    catalog.department = department
    catalog.frequency = "Monthly"
    catalog.evidence_required = evidence_required
    catalog.insert()
    return catalog.name


def _make_execution(*, task, execution_status, evidence_photo=None, findings=None):
    execution = frappe.new_doc("Safety Task Execution")
    execution.execution_date = "2026-01-05"
    execution.building = "_Test Building"
    execution.task = task
    execution.execution_status = execution_status
    if evidence_photo:
        execution.evidence_photo = evidence_photo
    for row in findings or []:
        execution.append("findings", row)
    return execution


class TestSafetyTaskExecution(FrappeTestCase):
    def test_a_failed_execution_on_an_evidence_required_task_without_a_photo_is_refused(self):
        """A failed check escalates to a Maintenance Request, so the failure needs proof."""
        task = _make_catalog_task(evidence_required=1)
        execution = _make_execution(task=task, execution_status="Poor")

        with self.assertRaisesRegex(frappe.ValidationError, "must carry a photo"):
            execution.insert()

    def test_a_failed_execution_on_an_evidence_required_task_with_a_photo_is_accepted(self):
        """The acceptance counterpart — attaching the required evidence must let it through."""
        task = _make_catalog_task(evidence_required=1)
        execution = _make_execution(
            task=task, execution_status="Poor", evidence_photo="/files/_test-evidence.jpg"
        )
        execution.insert()

        self.assertEqual(execution.evidence_photo, "/files/_test-evidence.jpg")

    def test_a_failed_execution_on_a_task_without_evidence_required_is_not_gated(self):
        """The photo requirement is scoped to catalog tasks flagged evidence_required —
        a failed result on a task that never asked for evidence must still save."""
        task = _make_catalog_task(evidence_required=0)
        execution = _make_execution(task=task, execution_status="Poor")

        execution.insert()

        self.assertIsNone(execution.evidence_photo)

    def test_submitting_a_failed_execution_raises_one_maintenance_request_and_cancelling_closes_it(self):
        """on_submit raises the building-scoped summary ticket for a failed result;
        on_cancel closes it again while it is still an untouched, Open draft."""
        task = _make_catalog_task(evidence_required=0)
        execution = _make_execution(task=task, execution_status="Not Done")
        execution.insert()
        execution.submit()

        self.assertTrue(execution.linked_maintenance_request)
        mr_name = execution.linked_maintenance_request
        self.assertEqual(
            frappe.db.get_value("Maintenance Request", mr_name, "source_execution"),
            execution.name,
        )
        self.assertEqual(frappe.db.get_value("Maintenance Request", mr_name, "status"), "Open")

        execution.cancel()

        self.assertEqual(frappe.db.get_value("Maintenance Request", mr_name, "status"), "Closed")

    def test_submitting_a_passing_execution_raises_no_maintenance_request(self):
        """The escalation is scoped to Poor / Not Done — a passing result must not spawn a
        repair ticket."""
        task = _make_catalog_task(evidence_required=0)
        execution = _make_execution(task=task, execution_status="Excellent")
        execution.insert()
        execution.submit()

        self.assertFalse(execution.linked_maintenance_request)
        self.assertEqual(
            frappe.db.count("Maintenance Request", {"source_execution": execution.name}), 0
        )

    def test_a_security_task_actionable_finding_without_a_photo_is_refused(self):
        """A Security-category finding may not drive an escalation without photo evidence,
        independent of the evidence_required / execution_status rule above."""
        task = _make_catalog_task(evidence_required=0, department="Security")
        execution = _make_execution(
            task=task,
            execution_status="Excellent",
            findings=[{"issue_type": "Structural", "room": "_T-101", "description": "_Test finding"}],
        )

        with self.assertRaisesRegex(frappe.ValidationError, "Security-category finding"):
            execution.insert()

    def test_a_security_task_actionable_finding_with_a_photo_is_accepted(self):
        """The acceptance counterpart — a photo lets the same Security escalation save."""
        task = _make_catalog_task(evidence_required=0, department="Security")
        execution = _make_execution(
            task=task,
            execution_status="Excellent",
            evidence_photo="/files/_test-security-evidence.jpg",
            findings=[{"issue_type": "Structural", "room": "_T-101", "description": "_Test finding"}],
        )

        execution.insert()

        self.assertEqual(execution.evidence_photo, "/files/_test-security-evidence.jpg")
