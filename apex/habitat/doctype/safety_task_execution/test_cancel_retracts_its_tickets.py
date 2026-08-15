# Copyright (c) 2026, AFMCO and contributors
"""cancelling a safety task execution must retract the tickets it raised.

Submitting an execution with a Poor / Not Done result raises Maintenance Requests: one
per actionable finding through `finding_fanout`, plus one building-scoped summary ticket.
Both stamp `source_execution` back at this document. Nothing undid them — the controller
had `on_submit` and no `on_cancel` — so cancelling the paperwork left live repair work
addressed to a building, with no record that the finding behind it had been withdrawn.

The proof is a sequence: submit, observe the tickets, cancel, observe them closed. The
boundary matters as much as the undo, so the second test progresses a ticket first and
requires it to survive — a technician who has picked up work owns it, and retracting the
document behind them must not reach into it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

FAILING_RESULT = "Poor"


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestCancellingAnExecutionRetractsItsTickets(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "STE " + _h()}
        ).insert(ignore_permissions=True).name
        cls.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "STE " + _h(),
                "site": cls.site,
                "status": "Active",
                "total_capacity": 4,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        cls.room = frappe.get_doc(
            {
                "doctype": "Room",
                "room_number": "STE" + _h(4),
                "building": cls.building,
                "capacity": 2,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        cls.task = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_name": "STE " + _h(),
                "evidence_required": 0,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        # The fixture is COMMITTED so the cancel path, which commits, cannot leave half
        # of it behind. That puts it past the class rollback, so the class owns its
        # removal outright. Class cleanups run LIFO and FrappeTestCase registered its
        # rollback first (so it runs last), which means this commit — registered BEFORE
        # the deletes — runs AFTER them and is what makes the removal stick.
        cls.addClassCleanup(frappe.db.commit)
        for doctype, name in (
            ("Safety Task Catalog", cls.task),
            ("Room", cls.room),
            ("Building", cls.building),
            ("Site", cls.site),
        ):
            cls.addClassCleanup(
                frappe.delete_doc, doctype, name, force=True, ignore_permissions=True
            )
        frappe.db.commit()

    def _submitted_execution(self):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": self.building,
                "task": self.task,
                "execution_date": today(),
                "execution_status": FAILING_RESULT,
                "findings": [
                    {
                        "room": self.room,
                        "issue_type": "Other",
                        "priority": "Medium",
                        "description": "_T fixture finding",
                        "status": "Open",
                    }
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        doc.submit()
        self.addCleanup(self._drop, doc.name)
        return doc

    def _drop(self, execution):
        for name in self._tickets(execution):
            frappe.db.set_value(
                "Maintenance Request", name, "docstatus", 0, update_modified=False
            )
            frappe.delete_doc(
                "Maintenance Request", name, force=True, ignore_permissions=True
            )
        frappe.db.set_value(
            "Safety Task Execution", execution, "docstatus", 0, update_modified=False
        )
        frappe.delete_doc(
            "Safety Task Execution", execution, force=True, ignore_permissions=True
        )

    def _tickets(self, execution):
        return frappe.get_all(
            "Maintenance Request", filters={"source_execution": execution}, pluck="name"
        )

    def _statuses(self, execution):
        return sorted(
            r.status
            for r in frappe.get_all(
                "Maintenance Request",
                filters={"source_execution": execution},
                fields=["status"],
            )
        )

    def test_submitting_raises_tickets_that_cancelling_closes(self):
        doc = self._submitted_execution()
        self.assertTrue(
            self._tickets(doc.name),
            "the fixture must actually raise a ticket, or there is nothing to retract",
        )
        self.assertEqual(set(self._statuses(doc.name)), {"Open"})

        doc.cancel()

        self.assertEqual(
            set(self._statuses(doc.name)),
            {"Closed"},
            "cancelling the execution left a live repair ticket behind",
        )

    def test_a_ticket_someone_has_picked_up_is_left_alone(self):
        """The boundary. A retraction closes untouched work, never work in progress."""
        doc = self._submitted_execution()
        tickets = self._tickets(doc.name)
        self.assertTrue(tickets)
        claimed = tickets[0]
        frappe.db.set_value("Maintenance Request", claimed, "status", "In Progress")

        doc.cancel()

        self.assertEqual(
            frappe.db.get_value("Maintenance Request", claimed, "status"),
            "In Progress",
            "a ticket a technician had already started was retracted underneath them",
        )
