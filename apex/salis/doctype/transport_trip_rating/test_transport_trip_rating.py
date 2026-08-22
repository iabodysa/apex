# Copyright (c) 2026, afmcoltd
"""What a Transport Trip Rating guarantees, asserted against the DocType itself.

The controller itself carries no validation — its one guarantee is the
DB-level backstop ``on_doctype_update`` adds: a composite UNIQUE index on
``(employee, dispatch_trip)`` (``unique_ttr_employee_trip``), so one worker
cannot rate the same trip twice even if a double-tap on the portal races past
a check-then-insert.

``test_records.json``'s row 0 (employee _T-Employee-00001, dispatch_trip
DT-000001) is already standing before any test method runs, so a second copy
of it is the negative control for that index.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Employee", "Dispatch Trip"]


class TestTransportTripRating(FrappeTestCase):
    def test_a_second_rating_from_the_same_worker_for_the_same_trip_is_refused(self):
        """One worker's rating of one trip must never be counted twice."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Transport Trip Rating")[0])
        self.assertRaisesRegex(
            frappe.UniqueValidationError,
            "unique_ttr_employee_trip",
            duplicate.insert,
        )
