# Copyright (c) 2026, afmcoltd
"""What a Boarding Scan Log guarantees, asserted against the DocType itself.

Every scan-validate attempt against a Dispatch Trip's QR boarding pass leaves an
append-only audit row: ``scanned_at`` is stamped at insert when the caller did not
already supply one, and the row refuses any edit once written, so the scan trail
can never be rewritten after the fact.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

test_dependencies = []


class TestBoardingScanLog(FrappeTestCase):
    def test_scanned_at_is_stamped_when_not_provided(self):
        """A scan with no timestamp must still leave a dated record in the trail."""
        log = frappe.copy_doc(frappe.get_test_records("Boarding Scan Log")[0])
        log.scanned_at = None
        log.insert()
        self.assertIsNotNone(log.scanned_at)

    def test_a_provided_scanned_at_is_not_overwritten(self):
        """A caller who already knows the scan time must not have it silently replaced."""
        log = frappe.copy_doc(frappe.get_test_records("Boarding Scan Log")[0])
        stamp = now_datetime()
        log.scanned_at = stamp
        log.insert()
        self.assertEqual(log.scanned_at, stamp)

    def test_editing_a_row_after_it_is_written_is_refused(self):
        """The scan trail is a log, not a transaction, and must not be rewritable."""
        log = frappe.copy_doc(frappe.get_test_records("Boarding Scan Log")[0])
        log.insert()
        log.notes = "amended after the fact"
        self.assertRaisesRegex(
            frappe.ValidationError,
            "append-only and cannot be edited",
            log.save,
        )
