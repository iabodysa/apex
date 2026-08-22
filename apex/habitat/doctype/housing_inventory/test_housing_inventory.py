# Copyright (c) 2026, afmcoltd
"""What Housing Inventory guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``before_save`` and the
``reflect_completed_maintenance`` hook function. ``before_save`` recomputes
``quantity_variance`` from the counted/expected quantities on every save, and stamps
``last_count_date`` only when the counted quantity actually changes — not on an
unrelated edit. ``reflect_completed_maintenance`` is fired from a Maintenance Work
Order's completion chokepoint (``mark_completed``, which writes via ``db_set`` and so
fires no ``on_update`` doc_event); it is called here directly with a stub carrying the
same attributes the real Work Order would, since Maintenance Work Order ships no
fixture of its own. It is idempotent and order-safe: a later call with an earlier
completion date must never roll the stamped date backward or double-count.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, today

from apex.habitat.doctype.housing_inventory.housing_inventory import (
    reflect_completed_maintenance,
)

test_dependencies = ["Building", "Room"]
# "Facility Asset" and "Maintenance Request" are deliberately absent: both reach, via
# their own link fields (Facility Asset -> Asset -> Journal Entry; Maintenance Request
# -> Cost Center / Asset), Payment Order -> Payment Request -> Payment Gateway Account
# -> Payment Gateway, a DocType this bench does not have installed (the "Payments" app
# is not present) — declaring either here makes this module unrunnable. Both records
# this test needs are built directly below, which only requires the Building/Room/User
# values they actually set, never the unused Asset-bridge or Cost-Center links.


class TestHousingInventory(FrappeTestCase):
    def test_quantity_variance_is_recomputed_and_the_count_date_only_moves_on_a_real_count(self):
        """The variance must track the two quantities; the count date must track only itself."""
        record = frappe.copy_doc(frappe.get_test_records("Housing Inventory")[0])
        record.insert()
        self.assertEqual(record.quantity_variance, 0)
        self.assertEqual(record.last_count_date, getdate(today()))

        record.db_set("last_count_date", "2020-01-01")
        record.reload()
        record.counted_quantity = 1
        record.save()
        self.assertEqual(record.quantity_variance, -1)
        self.assertEqual(
            record.last_count_date, getdate(today()), "a changed count must restamp the date"
        )

        record.db_set("last_count_date", "2020-01-01")
        record.reload()
        record.notes = "Unrelated note, no recount"
        record.save()
        self.assertEqual(
            record.last_count_date,
            getdate("2020-01-01"),
            "an edit that does not touch the counted quantity must not restamp it",
        )

    def test_a_completed_work_order_advances_the_matching_inventory_rows(self):
        """The acceptance case: a completion reflects onto every row on that asset."""
        asset = frappe.copy_doc(frappe.get_test_records("Facility Asset")[0])
        asset.asset_name = f"_T-Reflect Asset {frappe.generate_hash(length=6)}"
        asset.insert()

        request = frappe.copy_doc(frappe.get_test_records("Maintenance Request")[0])
        request.insert()
        frappe.db.set_value(
            "Maintenance Request", request.name, "related_facility_asset", asset.name
        )

        record = frappe.copy_doc(frappe.get_test_records("Housing Inventory")[0])
        record.facility_asset = asset.name
        record.condition = "Needs Maintenance"
        record.status = "Under Maintenance"
        record.insert()

        stub = frappe._dict(
            status="Completed",
            maintenance_request=request.name,
            actual_end_date="2026-02-01",
            name="_T-Stub-Work-Order-0001",
        )
        reflect_completed_maintenance(stub)

        reloaded = frappe.get_doc("Housing Inventory", record.name)
        self.assertEqual(reloaded.condition, "Good")
        self.assertEqual(reloaded.status, "Active")
        self.assertEqual(reloaded.maintenance_count, 1)
        self.assertEqual(reloaded.last_maintenance_work_order, stub.name)
        self.assertEqual(getdate(reloaded.last_maintenance_date), getdate("2026-02-01"))

        earlier_stub = frappe._dict(
            status="Completed",
            maintenance_request=request.name,
            actual_end_date="2026-01-15",
            name="_T-Stub-Work-Order-0002",
        )
        reflect_completed_maintenance(earlier_stub)

        unmoved = frappe.get_doc("Housing Inventory", record.name)
        self.assertEqual(
            unmoved.maintenance_count,
            1,
            "an out-of-order, earlier completion must not double-count",
        )
        self.assertEqual(
            getdate(unmoved.last_maintenance_date),
            getdate("2026-02-01"),
            "an out-of-order, earlier completion must not roll the stamped date back",
        )
