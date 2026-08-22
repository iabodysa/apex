# Copyright (c) 2026, afmcoltd
"""What a Trip Boarding Ledger guarantees, asserted against the DocType itself.

A posted row is immutable: any save of an already-persisted row is refused,
only the initial insert is allowed through. The one-boarding-outcome-per-
worker-per-trip guarantee is meant to be a DB-level backstop —
``on_doctype_update``'s composite UNIQUE index on ``(dispatch_trip, employee,
reversal_of)`` (``unique_tbl_trip_employee``) — but it does not hold. Same
defect class as Rental Accrual Ledger's (see that DocType's test): the
docstring assumes ``reversal_of`` is "NOT NULL DEFAULT ''", but ``describe``
shows it is a plain nullable column (``varchar(140) NULL DEFAULT NULL``), and
every original row leaves it NULL — so two original rows for the same trip
and worker do NOT collide, because SQL never treats two NULLs as equal. The
same shared assumption also appears (unverified here, out of this file's
write scope) in Facility Asset Movement Ledger and Maintenance Cost Ledger
under habitat, which use the identical ``add_unique_guarded(..., ["...",
"reversal_of"])`` shape — a defect CLASS, not a one-off.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


class TestTripBoardingLedger(FrappeTestCase):
    def test_editing_a_posted_row_is_refused(self):
        """A posted boarding outcome is an audit record; it must never be silently rewritten."""
        ledger = frappe.copy_doc(frappe.get_test_records("Trip Boarding Ledger")[0])
        ledger.insert()
        ledger.outcome = "No Show"
        self.assertRaisesRegex(
            frappe.PermissionError,
            "cannot be edited",
            ledger.save,
        )

    def test_a_second_original_row_for_the_same_trip_and_worker_is_refused(self):
        """One worker's outcome on one trip must never post twice — see module docstring."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Trip Boarding Ledger")[0])
        self.assertRaisesRegex(
            frappe.UniqueValidationError,
            "unique_tbl_trip_employee",
            duplicate.insert,
        )
