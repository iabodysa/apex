# Copyright (c) 2026, afmcoltd
"""What a Fuel Daily Log guarantees, asserted against the DocType itself.

A vehicle's odometer reading may not run backwards: a new log dated on or
after an earlier one may not carry a lower reading than that earlier log
already recorded for the same vehicle. The comparison is against the logs
themselves (this DocType is not submittable and carries no denormalized
"last odometer" field), so the boundary is exactly "not lower than the
latest reading on or before this log's own date" — an equal or higher
reading passes.

``test_records.json``'s own row 0 (vehicle VEH-000001, 2026-01-10, odometer
12000) is already standing before any test method runs, so it is the "last
reading" every test here compares a later date against.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]


class TestFuelDailyLog(FrappeTestCase):
    def test_a_lower_odometer_than_the_last_reading_is_refused(self):
        """A typo'd lower reading must not silently under-report the vehicle's distance."""
        log = frappe.copy_doc(frappe.get_test_records("Fuel Daily Log")[0])
        log.log_date = "2026-01-11"
        log.odometer = 11000
        self.assertRaisesRegex(
            frappe.ValidationError,
            "is lower than the last reading",
            log.insert,
        )

    def test_an_odometer_equal_to_the_last_reading_is_accepted(self):
        """The boundary is inclusive: equal to the last reading is not "running backwards"."""
        log = frappe.copy_doc(frappe.get_test_records("Fuel Daily Log")[0])
        log.log_date = "2026-01-12"
        log.odometer = 12000
        log.insert()
        self.assertEqual(log.odometer, 12000)

    def test_a_higher_odometer_than_the_last_reading_is_accepted(self):
        """The normal case: distance travelled since the last reading is always allowed through."""
        log = frappe.copy_doc(frappe.get_test_records("Fuel Daily Log")[0])
        log.log_date = "2026-01-13"
        log.odometer = 12500
        log.insert()
        self.assertEqual(log.odometer, 12500)
