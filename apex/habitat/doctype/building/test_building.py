# Copyright (c) 2026, afmcoltd
"""What Building guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``before_save`` and
``on_update``. Two guarantees are load-bearing enough to name in the controller's own
docstring: the abbreviation is LOCKED once a room exists under it (the room generator
keys on that string and never renames, so changing it would orphan every generated
room), and the ``responsible_supervisor`` field is mirrored onto a building-scoped
``User Permission`` row so a supervisor is never left holding stale access, or none.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Site", "Company"]


class TestBuilding(FrappeTestCase):
    def test_changing_the_abbreviation_once_a_room_exists_is_refused(self):
        """Rooms are keyed on the abbreviation string; renaming it would orphan them."""
        building = frappe.copy_doc(frappe.get_test_records("Building")[0])
        building.building_name = "_T-Abbrev Lock Building"
        building.abbreviation = "TALB"
        building.floor_plan = []
        building.insert()
        frappe.get_doc(
            {
                "doctype": "Room",
                "building": building.name,
                "room_number": "_T-Abbrev-Lock-101",
            }
        ).insert()

        building.abbreviation = "CHANGED"
        with self.assertRaisesRegex(frappe.ValidationError, "locked"):
            building.save()

    def test_changing_the_abbreviation_with_no_rooms_yet_is_accepted(self):
        """A building that has generated nothing yet is free to change its code."""
        building = frappe.copy_doc(frappe.get_test_records("Building")[0])
        building.building_name = "_T-Abbrev Free Building"
        building.abbreviation = "TAFB"
        building.floor_plan = []
        building.insert()

        building.abbreviation = "CHANGED"
        building.save()

        self.assertEqual(
            frappe.db.get_value("Building", building.name, "abbreviation"), "CHANGED"
        )

    def test_setting_a_supervisor_grants_them_a_building_scoped_user_permission(self):
        """The supervisor field and the User Permission row it mirrors must never drift apart."""
        building = frappe.copy_doc(frappe.get_test_records("Building")[0])
        building.building_name = "_T-Supervisor Building"
        building.floor_plan = []
        building.responsible_supervisor = "test2@example.com"
        building.insert()

        self.assertTrue(
            frappe.db.exists(
                "User Permission",
                {
                    "user": "test2@example.com",
                    "allow": "Building",
                    "for_value": building.name,
                },
            )
        )

    def test_replacing_a_supervisor_drops_the_old_grant_and_adds_the_new_one(self):
        """A supervisor who is replaced must not keep access to a building they no longer hold."""
        building = frappe.copy_doc(frappe.get_test_records("Building")[0])
        building.building_name = "_T-Supervisor Handover Building"
        building.floor_plan = []
        building.responsible_supervisor = "test2@example.com"
        building.insert()

        building.responsible_supervisor = "test3@example.com"
        building.save()

        self.assertFalse(
            frappe.db.exists(
                "User Permission",
                {
                    "user": "test2@example.com",
                    "allow": "Building",
                    "for_value": building.name,
                },
            ),
            "the previous supervisor's grant must be dropped",
        )
        self.assertTrue(
            frappe.db.exists(
                "User Permission",
                {
                    "user": "test3@example.com",
                    "allow": "Building",
                    "for_value": building.name,
                },
            ),
            "the new supervisor must be granted access",
        )
