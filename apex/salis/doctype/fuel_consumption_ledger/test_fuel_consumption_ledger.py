# Copyright (c) 2026, afmcoltd
"""What a Fuel Consumption Ledger guarantees, asserted against the DocType itself.

The controller carries no validation of its own — it is a hidden,
machine-written ledger with no human create/write DocPerm. Its one real
guarantee is the DB-level backstop ``on_doctype_update`` adds: a composite
UNIQUE index on ``(source_type, source_name)`` (``unique_fcl_source``), so a
second row for the same originating record fails at the database level even
if the engine's own check-then-insert is bypassed by a race.

``test_records.json``'s row 0 (source_type "Fuel Request", source_name
"FR-TEST-0001") is already standing before any test method runs, so a second
copy of it is the negative control for that index.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Salis Vehicle", "Salis Driver"]


class TestFuelConsumptionLedger(FrappeTestCase):
    def test_a_second_row_for_the_same_source_is_refused(self):
        """One originating record must never post two ledger rows."""
        duplicate = frappe.copy_doc(frappe.get_test_records("Fuel Consumption Ledger")[0])
        self.assertRaisesRegex(
            frappe.UniqueValidationError,
            "unique_fcl_source",
            duplicate.insert,
        )
