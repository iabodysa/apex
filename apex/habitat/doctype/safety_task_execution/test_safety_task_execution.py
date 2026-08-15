# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests.factories import make_building, make_company, make_room

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestSafetyTaskExecution(FrappeTestCase):

    def test_docperm_safety_officer(self):
        """Safety Officer must have read/write/create on Safety Task Execution (no submit)."""
        meta = frappe.get_meta("Safety Task Execution")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Safety Officer", roles, "Safety Officer perm row is missing")
        p = roles["Safety Officer"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertEqual(p.create, 1)
        self.assertFalse(getattr(p, "submit", 0), "Safety Officer must NOT have submit on STE")

    def test_create_valid_execution(self):
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "naming_series": "STE-.YYYY.-.#####",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": "STC-QA-001",
            "execution_status": "Good",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.execution_status, "Good")
        frappe.delete_doc("Safety Task Execution", doc.name, force=True, ignore_permissions=True)


    def _evidence_task(self, evidence_required):
        """Create a Safety Task Catalog row with the given evidence flag."""
        return frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": f"STC-EV-{frappe.generate_hash(length=12)}",
            "task_title": "Evidence task",
            "department": "Fire Safety",
            "frequency": "Monthly",
            "evidence_required": evidence_required,
        }).insert(ignore_permissions=True).name

    def test_failed_evidence_task_without_photo_is_rejected(self):
        """A FAILED (Poor) result on an evidence_required task is blocked with no photo."""
        task = self._evidence_task(evidence_required=1)
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": task,
            "execution_status": "Poor",
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_not_done_evidence_task_without_photo_is_rejected(self):
        """Not Done is the second failing status and is also blocked with no photo."""
        task = self._evidence_task(evidence_required=1)
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": task,
            "execution_status": "Not Done",
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_failed_evidence_task_with_photo_passes(self):
        """A FAILED result on an evidence_required task saves once a photo is attached."""
        task = self._evidence_task(evidence_required=1)
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": task,
            "execution_status": "Poor",
            "evidence_photo": "/files/evidence.jpg",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.execution_status, "Poor")
        frappe.delete_doc(
            "Safety Task Execution", doc.name, force=True, ignore_permissions=True
        )

    def test_passing_evidence_task_without_photo_is_allowed(self):
        """A passing (Good) result is NOT gated even when the task is evidence_required:
        the photo proves a failure, and there is no failure to prove."""
        task = self._evidence_task(evidence_required=1)
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": task,
            "execution_status": "Good",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.execution_status, "Good")
        frappe.delete_doc(
            "Safety Task Execution", doc.name, force=True, ignore_permissions=True
        )

    def test_evidence_not_required_task_saves_without_photo(self):
        """A failing result with evidence_required=0 saves with no Evidence Photo."""
        task = self._evidence_task(evidence_required=0)
        doc = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": "2026-06-20",
            "building": "QA-BLDG",
            "task": task,
            "execution_status": "Poor",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.execution_status, "Poor")
        frappe.delete_doc(
            "Safety Task Execution", doc.name, force=True, ignore_permissions=True
        )


    def _exec_task(self):
        """A catalog task with no photo requirement so a failed execution can be
        submitted without an Evidence Photo (the escalation, not the photo gate,
        is under test here)."""
        return frappe.get_doc({
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_code": f"STC-MR-{frappe.generate_hash(length=12)}",
            "task_title": "Escalation task",
            "department": "Fire Safety",
            "frequency": "Monthly",
            "evidence_required": 0,
        }).insert(ignore_permissions=True).name

    def _failed_execution(self, building, task, status="Poor"):
        ste = frappe.get_doc({
            "doctype": "Safety Task Execution",
            "execution_date": today(),
            "building": building,
            "task": task,
            "execution_status": status,
        }).insert(ignore_permissions=True)
        ste.submit()
        ste.reload()
        return ste

    def test_poor_execution_raises_and_links_maintenance_request(self):
        """A Poor result raises ONE building-scoped Maintenance Request, links it
        on linked_maintenance_request, and stamps source_execution back."""
        make_company()
        building = make_building(name="MR Esc Bldg Poor").name
        make_room(building, room_number="MR-ESC-POOR-R01")
        task = self._exec_task()

        ste = self._failed_execution(building, task, "Poor")

        self.assertTrue(ste.linked_maintenance_request, "an MR should be linked")
        mr = frappe.get_doc("Maintenance Request", ste.linked_maintenance_request)
        self.assertEqual(mr.building, building)
        self.assertEqual(mr.source_execution, ste.name)
        self.assertEqual(mr.status, "Open")
        self.assertEqual(
            frappe.db.count("Maintenance Request", {"source_execution": ste.name}), 1
        )

    def test_not_done_execution_raises_maintenance_request(self):
        """Not Done is the second failing status and also escalates."""
        make_company()
        building = make_building(name="MR Esc Bldg NotDone").name
        make_room(building, room_number="MR-ESC-ND-R01")
        task = self._exec_task()

        ste = self._failed_execution(building, task, "Not Done")
        self.assertTrue(ste.linked_maintenance_request)

    def test_good_execution_raises_no_maintenance_request(self):
        """A passing (Good) result must NOT escalate to a Maintenance Request."""
        make_company()
        building = make_building(name="MR Esc Bldg Good").name
        make_room(building, room_number="MR-ESC-GOOD-R01")
        task = self._exec_task()

        ste = self._failed_execution(building, task, "Good")
        self.assertFalse(ste.linked_maintenance_request, "Good must not escalate")
        self.assertEqual(
            frappe.db.count("Maintenance Request", {"source_execution": ste.name}), 0
        )

    def test_escalation_is_idempotent_on_rerun(self):
        """A defensive re-run of the escalation on an already-linked execution must
        NOT create a second summary MR — the linked_maintenance_request guard
        short-circuits once a live ticket exists."""
        make_company()
        building = make_building(name="MR Esc Bldg Rerun").name
        make_room(building, room_number="MR-ESC-RERUN-R01")
        task = self._exec_task()

        ste = self._failed_execution(building, task, "Poor")
        first_mr = ste.linked_maintenance_request
        self.assertTrue(first_mr)

        ste._escalate_failed_execution()
        ste.reload()

        self.assertEqual(ste.linked_maintenance_request, first_mr, "link unchanged")
        self.assertEqual(
            frappe.db.count("Maintenance Request", {"source_execution": ste.name}), 1,
            "re-run must not spawn a second summary ticket",
        )

    def test_no_room_in_building_skips_escalation_gracefully(self):
        """Maintenance Request.room is mandatory; a building with no rooms cannot
        carry the summary ticket, so submit still succeeds and nothing is linked."""
        make_company()
        building = make_building(name="MR Esc Bldg NoRoom").name
        task = self._exec_task()

        ste = self._failed_execution(building, task, "Poor")
        self.assertFalse(
            ste.linked_maintenance_request,
            "no room -> no summary MR, but submit must not fail",
        )
