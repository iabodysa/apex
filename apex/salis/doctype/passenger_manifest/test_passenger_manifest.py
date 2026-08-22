# Copyright (c) 2026, afmcoltd
"""What a Passenger Manifest guarantees, asserted against the DocType itself.

One employee cannot appear twice in the same manifest's passenger list, and
``passenger_count`` is always recomputed from the passengers table rather than
trusted as typed.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Salis Driver", "Employee"]


class TestPassengerManifest(FrappeTestCase):
    def test_the_same_employee_twice_in_one_manifest_is_refused(self):
        """One employee cannot be counted, or boarded, twice on the same trip."""
        manifest = frappe.copy_doc(frappe.get_test_records("Passenger Manifest")[0])
        manifest.append("passengers", {"employee": "_T-Employee-00001", "passenger_name": "A"})
        manifest.append("passengers", {"employee": "_T-Employee-00001", "passenger_name": "B"})
        self.assertRaisesRegex(
            frappe.ValidationError,
            "appears more than once",
            manifest.insert,
        )

    def test_passenger_count_is_recomputed_from_the_passengers_table(self):
        """A hand-set passenger count must not survive save; it always reflects the real rows."""
        manifest = frappe.copy_doc(frappe.get_test_records("Passenger Manifest")[0])
        manifest.passenger_count = 999
        manifest.append("passengers", {"passenger_name": "_T-Rider One"})
        manifest.append("passengers", {"passenger_name": "_T-Rider Two"})
        manifest.insert()
        self.assertEqual(manifest.passenger_count, 2)
