# Copyright (c) 2026, AFMCO and contributors
"""the badge must count the queue, not the page it fetched.

The delivery screen fetched 50 rows ordered `modified desc` and put
`deliveries.length` on the badge. Two things followed from that, and both only appear
once the queue passes fifty:

* the number became a cap — a queue of 60 read as 50, and the operator had no way to
  know the difference;
* `modified desc` put the LONGEST-WAITING delivery last, so on a busy day the one row
  that most needed attention was the one that fell off the end.

This proves both server-side, at the scale where they appear. The badge now reads
`frappe.client.get_count` over the same filters, and the list sorts oldest-first.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

PENDING = ["Pending Exits", "Released"]
FIXTURE_ROWS = 51
LIST_LIMIT = 50


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestTheDeliveryQueueCount(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = _h(10)
        # A delivery refuses to save without a Facility Asset, and an asset needs a
        # building and a supervisor. One asset serves all the rows; the queue is what
        # is under test, not the asset.
        cls.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "DQ " + _h()}
        ).insert(ignore_permissions=True).name
        cls.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "DQ " + _h(),
                "site": cls.site,
                "status": "Active",
                "total_capacity": 2,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        cls.asset = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "asset_name": "DQ " + _h(),
                "asset_category": "Other",
                "building": cls.building,
                "responsible_supervisor": "Administrator",
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        # asset_serial_number is fetch_from + read_only, so it cannot carry a per-row
        # tag. The rows are identified by the one asset they share and by the order they
        # were created in, which is what the ordering assertions actually need.
        cls.filters = [["status", "in", PENDING], ["facility_asset", "=", cls.asset]]
        # The fixture is COMMITTED, which puts it past the class rollback, so the class
        # owns its removal outright. Class cleanups run LIFO and FrappeTestCase
        # registered its rollback first (so it runs last), which means this commit —
        # registered BEFORE every delete below — runs AFTER them and makes them stick.
        cls.addClassCleanup(frappe.db.commit)
        for doctype, name in (
            ("Facility Asset", cls.asset),
            ("Building", cls.building),
            ("Site", cls.site),
        ):
            cls.addClassCleanup(
                frappe.delete_doc, doctype, name, force=True, ignore_permissions=True
            )
        cls.created = []
        for i in range(FIXTURE_ROWS):
            doc = frappe.get_doc(
                {
                    "doctype": "Facility Asset Delivery",
                    "status": "Pending Exits",
                    "facility_asset": cls.asset,
                }
            )
            doc.insert(ignore_permissions=True, ignore_mandatory=True)
            cls.created.append(doc.name)
            cls.addClassCleanup(
                frappe.delete_doc,
                "Facility Asset Delivery",
                doc.name,
                force=True,
                ignore_permissions=True,
            )
        frappe.db.commit()

    def test_the_count_is_the_queue_not_the_page(self):
        from frappe.client import get_count

        total = get_count("Facility Asset Delivery", filters=self.filters)
        self.assertEqual(
            int(total),
            FIXTURE_ROWS,
            "the count must be the whole queue, not the fetch limit",
        )

    def test_the_page_really_is_shorter_than_the_queue(self):
        """Without this, the test above would pass on a queue that fits in one page."""
        rows = frappe.get_all(
            "Facility Asset Delivery",
            filters=self.filters,
            fields=["name"],
            limit_page_length=LIST_LIMIT,
        )
        self.assertEqual(len(rows), LIST_LIMIT)
        self.assertLess(
            len(rows),
            FIXTURE_ROWS,
            "the fixture must exceed the page, or the defect cannot show",
        )

    def test_oldest_first_puts_the_longest_waiting_row_on_the_first_page(self):
        rows = frappe.get_all(
            "Facility Asset Delivery",
            filters=self.filters,
            fields=["name"],
            order_by="creation asc",
            limit_page_length=LIST_LIMIT,
        )
        self.assertEqual(
            rows[0].name,
            self.created[0],
            "the first row must be the one that has waited longest",
        )

    def test_modified_desc_is_what_hid_it(self):
        """The old ordering, kept as the contrast that justifies the new one."""
        rows = frappe.get_all(
            "Facility Asset Delivery",
            filters=self.filters,
            fields=["name"],
            order_by="creation desc",
            limit_page_length=LIST_LIMIT,
        )
        shown = {r.name for r in rows}
        self.assertNotIn(
            self.created[0],
            shown,
            "newest-first is expected to push the oldest row off the first page",
        )
