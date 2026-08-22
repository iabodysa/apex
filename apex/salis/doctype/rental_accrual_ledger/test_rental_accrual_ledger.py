# Copyright (c) 2026, afmcoltd
"""What a Rental Accrual Ledger guarantees, asserted against the DocType itself.

The controller carries no validation of its own — it is a hidden,
machine-written daily memo with no human create/write DocPerm. Its one real
guarantee is meant to be the DB-level backstop ``on_doctype_update`` adds: a
composite UNIQUE index on ``(vehicle, accrual_date, reversal_of)``
(``unique_ral_vehicle_date``), so a second original row for the same vehicle
and day should fail at the database level even if the engine's own
check-then-insert is bypassed by a race.

That intent does not hold. ``reversal_of`` is a plain nullable Link column
(``describe`` shows ``varchar(140) NULL DEFAULT NULL``, not the "NOT NULL
DEFAULT ''" the controller's own docstring assumes), and every original row
leaves it NULL. SQL unique indexes never treat two NULLs as equal, so two
original rows for the same vehicle and day — both with ``reversal_of`` NULL —
do NOT collide, and the "hard idempotency backstop" the docstring promises
does not exist for the exact case (an original posting) it is meant to cover.
This test pins the intended contract and fails against it, rather than
asserting the gap as if it were the guarantee.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle"]


class TestRentalAccrualLedger(FrappeTestCase):
    def test_a_second_original_row_for_the_same_vehicle_and_day_is_refused(self):
        """One vehicle-day must never post two original accrual rows — see module docstring."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Rental Accrual Ledger")[0])
        self.assertRaisesRegex(
            frappe.UniqueValidationError,
            "unique_ral_vehicle_date",
            duplicate.insert,
        )
