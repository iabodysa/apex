# Copyright (c) 2026, AFMCO and contributors
"""v0.8.4 — Assigning an Accommodation Resident Request to a user creates a native
ToDo follow-up for that user; resolving/closing the request closes the ToDo. The
ToDo creation is idempotent (no duplicate per assignee)."""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase


def _open_todos(name, user="Administrator"):
    return frappe.get_all("ToDo", filters={
        "reference_type": "Accommodation Resident Request", "reference_name": name,
        "allocated_to": user, "status": "Open"})


class TestResidentRequestToDo(ApexHabitatTestCase):
    def _new_request(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Resident Request",
            "request_category": "Maintenance",
            "description": "Test request " + frappe.generate_hash(length=4),
            "status": "New",
        })
        doc.insert(ignore_permissions=True)
        return doc

    def test_assign_creates_todo_then_resolve_closes_it(self):
        doc = self._new_request()
        self.assertEqual(len(_open_todos(doc.name)), 0)

        doc.status = "Assigned"
        doc.assigned_to = "Administrator"
        doc.save(ignore_permissions=True)
        self.assertEqual(len(_open_todos(doc.name)), 1, "assigning must create one ToDo")

        # Idempotent: saving again does not create a second ToDo.
        doc.save(ignore_permissions=True)
        self.assertEqual(len(_open_todos(doc.name)), 1, "no duplicate ToDo on re-save")

        doc.status = "Resolved"
        doc.resolution_notes = "Done"
        doc.save(ignore_permissions=True)
        self.assertEqual(len(_open_todos(doc.name)), 0, "resolving must close the ToDo")
