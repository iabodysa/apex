# Copyright (c) 2026, afmcoltd
"""What a Room guarantees, asserted against the DocType itself.

Patterned on frappe's own permission/whitelisted-method tests
(``frappe/tests/test_document.py``, ``test_permission``). The ``Room`` controller class
carries no lifecycle hooks; the one guarantee lives in the whitelisted
``toggle_service`` — a room with a current occupant cannot be pulled out of service, the
same "no occupied-and-out-of-service state" rule Housing Assignment's own submit/cancel
enforces from the other side.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.room.room import toggle_service

test_dependencies = ["Building", "Bed", "Employee", "Project", "Housing Assignment"]


class TestRoom(FrappeTestCase):
    def test_toggle_service_flips_an_unoccupied_room_between_ready_and_out_of_service(self):
        """An unoccupied room must be free to move either direction — the guard only
        applies to rooms carrying an occupant."""
        room = "_T-102"
        self.assertEqual(frappe.db.get_value("Room", room, "readiness_status"), "Ready")

        self.assertEqual(toggle_service(room), "Out of Service")
        self.assertEqual(
            frappe.db.get_value("Room", room, "readiness_status"), "Out of Service"
        )

        self.assertEqual(toggle_service(room), "Ready")
        self.assertEqual(frappe.db.get_value("Room", room, "readiness_status"), "Ready")

    def test_toggle_service_refuses_a_room_with_a_current_occupant(self):
        """Deactivating an occupied room would leave that occupant in a room nobody can
        service; relocate or check them out first."""
        assignment = frappe.copy_doc(frappe.get_test_records("Housing Assignment")[0])
        assignment.insert()
        assignment.submit()
        self.addCleanup(assignment.cancel)

        with self.assertRaisesRegex(frappe.ValidationError, "current occupant"):
            toggle_service(assignment.room)

        self.assertEqual(
            frappe.db.get_value("Room", assignment.room, "readiness_status"), "Ready"
        )
