# Copyright (c) 2026, afmcoltd
"""What a Room Bed Transfer guarantees, asserted against the DocType itself.

Patterned on frappe's own submittable-document lifecycle tests
(``frappe/tests/test_document.py``, ``test_update_after_submit``). No ``test_records.json``
exists for this DocType (``frappe.get_test_records`` returns ``[]`` for it — confirmed in
``frappe/__init__.py``), so every case here builds its subject with ``frappe.new_doc``
inside the test method, never a module-level fixture.

Room Bed Transfer is the in-place move this app's own docstring calls one of the three
funnels through Housing Assignment's ``recalculate_spatial`` (the other two are Housing
Assignment's own submit/cancel and Housing Checkout's). Its guarantees: ``on_submit`` moves
the live assignment and swaps both beds' status; ``before_submit`` refuses to move a
resident who is not actually on the bed the transfer was raised from; ``validate`` refuses
a target bed that is already taken; ``before_cancel`` refuses to reverse a transfer once
the source assignment can no longer confirm the resident is where the reversal assumes.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Room", "Bed", "Employee", "Project", "Housing Assignment"]


def _retire(doctype, name):
    """Cleanup helper: cancels a submitted document, deletes a draft one, and does
    nothing for a name that was never actually persisted (autoname can populate
    ``.name`` before ``validate`` aborts the insert)."""
    if not name:
        return
    docstatus = frappe.db.get_value(doctype, name, "docstatus")
    if docstatus == 1:
        frappe.get_doc(doctype, name).cancel()
    elif docstatus is not None:
        frappe.delete_doc(doctype, name, ignore_permissions=True)


class TestRoomBedTransfer(FrappeTestCase):
    def test_submitting_a_transfer_moves_the_assignment_and_swaps_bed_status(self):
        """on_submit is the only thing that actually moves the resident: it re-points the
        live assignment and swaps both beds' status under lock; on_cancel must reverse
        both exactly."""
        assignment = frappe.copy_doc(frappe.get_test_records("Housing Assignment")[0])
        assignment.insert()
        assignment.submit()
        self.addCleanup(_retire, "Housing Assignment", assignment.name)

        transfer = frappe.new_doc("Room Bed Transfer")
        transfer.naming_series = "RBT-.YYYY.-.####"
        transfer.assignment = assignment.name
        transfer.to_room = "_T-102"
        transfer.to_bed = "_T-102-A"
        transfer.transfer_date = frappe.utils.today()
        transfer.insert()
        self.assertEqual(transfer.from_bed, "_T-101-A", "fetch_from must pull the origin bed from the assignment")
        transfer.submit()
        self.addCleanup(_retire, "Room Bed Transfer", transfer.name)

        self.assertEqual(
            frappe.db.get_value("Housing Assignment", assignment.name, "bed"), "_T-102-A"
        )
        self.assertEqual(frappe.db.get_value("Bed", "_T-101-A", "status"), "Available")
        self.assertEqual(frappe.db.get_value("Bed", "_T-102-A", "status"), "Occupied")

        transfer.cancel()

        self.assertEqual(
            frappe.db.get_value("Housing Assignment", assignment.name, "bed"), "_T-101-A"
        )
        self.assertEqual(frappe.db.get_value("Bed", "_T-101-A", "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Bed", "_T-102-A", "status"), "Available")

    def test_submitting_a_transfer_after_the_source_bed_has_since_changed_is_refused(self):
        """``from_bed`` is ``fetch_from: assignment.bed`` and frozen (read-only) at the
        transfer's creation time, so ``before_submit`` re-reads the assignment's CURRENT
        bed at submit time — catching a second move that lands in between and would
        otherwise move the wrong occupant if only the frozen value were trusted."""
        assignment = frappe.copy_doc(frappe.get_test_records("Housing Assignment")[0])
        assignment.insert()
        assignment.submit()
        self.addCleanup(_retire, "Housing Assignment", assignment.name)

        transfer = frappe.new_doc("Room Bed Transfer")
        transfer.naming_series = "RBT-.YYYY.-.####"
        transfer.assignment = assignment.name
        transfer.to_room = "_T-102"
        transfer.to_bed = "_T-102-A"
        transfer.transfer_date = frappe.utils.today()
        transfer.insert()
        self.addCleanup(_retire, "Room Bed Transfer", transfer.name)
        self.assertEqual(transfer.from_bed, "_T-101-A")

        # a second, unrelated process moves the resident before this transfer submits
        frappe.db.set_value("Housing Assignment", assignment.name, "bed", "_T-101-B")
        self.addCleanup(
            frappe.db.set_value, "Housing Assignment", assignment.name, "bed", "_T-101-A"
        )

        with self.assertRaisesRegex(frappe.ValidationError, "resident is now in Bed"):
            transfer.submit()

    def test_a_transfer_to_an_already_occupied_bed_is_refused(self):
        """A second resident cannot be moved onto a bed someone is already in."""
        assignment = frappe.copy_doc(frappe.get_test_records("Housing Assignment")[0])
        assignment.insert()
        assignment.submit()
        self.addCleanup(_retire, "Housing Assignment", assignment.name)

        other_assignment = frappe.copy_doc(frappe.get_test_records("Housing Assignment")[1])
        other_assignment.insert()
        other_assignment.submit()
        self.addCleanup(_retire, "Housing Assignment", other_assignment.name)

        transfer = frappe.new_doc("Room Bed Transfer")
        transfer.naming_series = "RBT-.YYYY.-.####"
        transfer.assignment = assignment.name
        transfer.to_room = "_T-201"
        transfer.to_bed = "_T-201-A"
        transfer.transfer_date = frappe.utils.today()

        with self.assertRaisesRegex(frappe.ValidationError, "already occupied"):
            transfer.insert()

    def test_cancelling_a_transfer_after_the_resident_has_since_checked_out_is_refused(self):
        """before_cancel refuses to reverse a transfer once the resident has since checked
        out — reversing blind would re-occupy the origin bed for someone no longer housed
        at all."""
        self.addCleanup(frappe.db.set_value, "Bed", "_T-101-A", "status", "Available")
        self.addCleanup(frappe.db.set_value, "Bed", "_T-102-A", "status", "Available")

        assignment = frappe.copy_doc(frappe.get_test_records("Housing Assignment")[0])
        assignment.insert()
        assignment.submit()

        transfer = frappe.new_doc("Room Bed Transfer")
        transfer.naming_series = "RBT-.YYYY.-.####"
        transfer.assignment = assignment.name
        transfer.to_room = "_T-102"
        transfer.to_bed = "_T-102-A"
        transfer.transfer_date = frappe.utils.today()
        transfer.insert()
        transfer.submit()

        # a real Housing Checkout submission stamps this; simulated directly here since
        # Housing Checkout's own flow is out of this file's scope
        frappe.db.set_value(
            "Housing Assignment", assignment.name, "check_out_date", frappe.utils.today()
        )

        with self.assertRaisesRegex(frappe.ValidationError, "no longer be reversed"):
            transfer.cancel()
