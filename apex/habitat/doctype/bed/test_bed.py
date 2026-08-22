# Copyright (c) 2026, afmcoltd
"""What Bed guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_client.py`` — the subject is a whitelisted API
function, not the controller's own ``validate``/``on_submit`` (there is none; ``Bed``'s
class body is ``pass``). ``toggle_service`` is the one door between ``Available`` and
``Out of Service``, and it must refuse to open on an ``Occupied`` bed so a resident's
bed can never be taken out of service out from under them.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.bed.bed import toggle_service

test_dependencies = ["Building", "Room"]


class TestBed(FrappeTestCase):
    def test_toggle_service_flips_an_available_bed_to_out_of_service_and_back(self):
        """The one path between the two service states must actually swing both ways."""
        record = frappe.copy_doc(frappe.get_test_records("Bed")[0])
        record.bed_code = f"{record.bed_code}-TGL"
        record.insert()

        self.assertEqual(toggle_service(record.name), "Out of Service")
        self.assertEqual(
            frappe.db.get_value("Bed", record.name, "status"), "Out of Service"
        )

        self.assertEqual(toggle_service(record.name), "Available")
        self.assertEqual(
            frappe.db.get_value("Bed", record.name, "status"), "Available"
        )

    def test_toggle_service_refuses_an_occupied_bed(self):
        """An occupied bed cannot be pulled from service out from under its resident."""
        record = frappe.copy_doc(frappe.get_test_records("Bed")[0])
        record.bed_code = f"{record.bed_code}-OCC"
        record.insert()
        record.db_set("status", "Occupied")

        with self.assertRaisesRegex(frappe.ValidationError, "occupied"):
            toggle_service(record.name)

        self.assertEqual(
            frappe.db.get_value("Bed", record.name, "status"),
            "Occupied",
            "a refused toggle must leave the bed's status untouched",
        )
