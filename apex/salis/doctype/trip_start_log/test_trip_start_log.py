# Copyright (c) 2026, afmcoltd
"""What a Trip Start Log guarantees, asserted against the DocType itself.

No worker may board twice on the same trip, registered or unregistered.
``expected_count`` and ``boarded_count`` are always derived (from the linked
Transport Request's manifest and from the boarding rows), never hand-set.
``end_datetime`` cannot precede ``start_datetime``.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Dispatch Trip", "Employee"]


class TestTripStartLog(FrappeTestCase):
    def test_the_same_registered_worker_boarding_twice_is_refused(self):
        """A worker cannot be counted as boarded twice on one trip."""
        log = frappe.copy_doc(frappe.get_test_records("Trip Start Log")[0])
        log.append("boarding_events", {"worker": "_T-Employee-00001"})
        log.append("boarding_events", {"worker": "_T-Employee-00001"})
        self.assertRaisesRegex(
            frappe.ValidationError,
            "already boarded on this trip",
            log.insert,
        )

    def test_an_unregistered_worker_without_a_name_or_id_is_refused(self):
        """An unregistered boarding row must still identify who boarded, by name or id."""
        log = frappe.copy_doc(frappe.get_test_records("Trip Start Log")[0])
        log.append("boarding_events", {"is_unregistered": 1})
        self.assertRaisesRegex(
            frappe.ValidationError,
            "needs a name or a contractor/temp id",
            log.insert,
        )

    def test_boarded_count_is_derived_from_the_boarding_events_table(self):
        """A hand-set boarded count must not survive save; it always reflects the real rows."""
        log = frappe.copy_doc(frappe.get_test_records("Trip Start Log")[0])
        log.boarded_count = 999
        log.append("boarding_events", {"worker": "_T-Employee-00001"})
        log.append("boarding_events", {"is_unregistered": 1, "worker_name": "Contractor A"})
        log.insert()
        self.assertEqual(log.boarded_count, 2)

    def test_end_datetime_before_start_datetime_is_refused(self):
        """A trip cannot end before it started."""
        log = frappe.copy_doc(frappe.get_test_records("Trip Start Log")[0])
        log.start_datetime = "2026-01-10 06:00:00"
        log.end_datetime = "2026-01-10 05:00:00"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "cannot be earlier than Start Datetime",
            log.insert,
        )
