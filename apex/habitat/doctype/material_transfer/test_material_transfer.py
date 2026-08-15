# Copyright (c) 2026, afmcoltd
"""Material Transfer moves stock between two building stores on the Accommodation Stock Ledger:
submit ships out of the source (In Transit), mark_received lands it in the destination (Received),
cancel reverses every posted leg, and a receipt that crosses a cost centre memos finance.

Both buildings and the article come from ``test_records.json`` — the two fixture buildings already
carry different default cost centres, which is what the cross-cost-centre cases need. The previous
form of this file built a Company, a Site, two Cost Centres, two Buildings, a Custody Asset
Category and a Custody Article in ``setUp``, per test method, for seven test methods.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    post_stock_entry,
)
from apex.habitat.doctype.material_transfer.material_transfer import mark_received
from apex.habitat.report.accommodation_stock_balance.accommodation_stock_balance import (
    execute as stock_balance_report,
)

test_dependencies = ["Building", "Custody Article", "User"]

SOURCE = "_Test Building"
DESTINATION = "_Test Building 2"
# The memo is addressed to a PERSON, not a string: email_gate.mailable drops anyone who is not an
# enabled User with email notifications on, so a made-up address silently sends nothing. This one
# comes from Frappe's own User test_records.json.
FINANCE_RECIPIENT = "test@example.com"


class TestMaterialTransfer(FrappeTestCase):
    def setUp(self):
        self.article = frappe.db.get_value("Custody Article", {"article_name": "_Test Blanket"})
        self.source_cost_center = frappe.db.get_value("Building", SOURCE, "default_cost_center")
        self.destination_cost_center = frappe.db.get_value("Building", DESTINATION, "default_cost_center")
        # Habitat Settings is a Single, so a case that flips a toggle would otherwise hand the
        # next one a cached document that no longer matches the rolled-back row.
        self.addCleanup(frappe.clear_document_cache, "Habitat Settings", "Habitat Settings")
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so stock a case
        # leaves in a shared fixture store would become the next case's opening balance. A
        # savepoint is the framework's own way to hand the store back exactly as it was found.
        frappe.db.savepoint("apex_material_transfer_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_material_transfer_case")

    def _seed_source(self, qty):
        post_stock_entry(
            item_type="Custody Article", item=self.article, qty=qty, building=SOURCE,
            voucher_type="Opening Stock", voucher_no="OPEN-" + frappe.generate_hash(length=12).upper(),
        )

    def _transfer(self, qty=4):
        doc = frappe.get_doc({
            "doctype": "Material Transfer",
            "naming_series": "ACC-MTR-.YYYY.-.######",
            "transfer_date": "2026-05-01",
            "from_building": SOURCE,
            "to_building": DESTINATION,
        })
        doc.append("items", {"item_type": "Custody Article", "item": self.article, "qty": qty})
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def _set_finance_toggle(self, on, email=FINANCE_RECIPIENT):
        settings = frappe.get_single("Habitat Settings")
        settings.notify_finance_on_liability_transfer = 1 if on else 0
        settings.finance_notification_email = email if on else None
        settings.enable_email_notifications = 1 if on else 0
        settings.save(ignore_permissions=True)

    def _balance(self, building):
        return get_store_balance("Custody Article", self.article, building)

    def test_shipping_then_receiving_moves_the_stock_between_the_two_stores(self):
        self._seed_source(10)
        transfer = self._transfer(4)

        self.assertEqual(transfer.status, "In Transit")
        self.assertEqual(self._balance(SOURCE), 6.0)
        self.assertEqual(self._balance(DESTINATION), 0.0)

        mark_received(transfer.name, "2026-05-03")
        transfer.reload()

        self.assertEqual(transfer.status, "Received")
        self.assertEqual(self._balance(SOURCE), 6.0)
        self.assertEqual(self._balance(DESTINATION), 4.0)

    def test_a_transfer_larger_than_the_source_store_is_refused_at_submit(self):
        self._seed_source(2)

        with self.assertRaises(frappe.ValidationError):
            self._transfer(5)

    def test_cancelling_reverses_both_legs(self):
        self._seed_source(10)
        transfer = self._transfer(4)
        mark_received(transfer.name, "2026-05-03")
        transfer.reload()
        transfer.cancel()

        self.assertEqual(self._balance(SOURCE), 10.0)
        self.assertEqual(self._balance(DESTINATION), 0.0)

    def test_a_receipt_across_two_cost_centres_memos_finance_when_the_toggle_is_on(self):
        self.assertNotEqual(self.source_cost_center, self.destination_cost_center)
        self._set_finance_toggle(True)
        self._seed_source(10)
        transfer = self._transfer(4)

        with patch(
            "apex.habitat.doctype.material_transfer.material_transfer.frappe.sendmail"
        ) as sendmail:
            mark_received(transfer.name, "2026-05-03")

        self.assertEqual(sendmail.call_count, 1, "a finance memo must be sent on a cross-cost-centre receipt")
        self.assertEqual(sendmail.call_args.kwargs["recipients"], [FINANCE_RECIPIENT])

    def test_no_memo_is_sent_when_the_toggle_is_off(self):
        self._set_finance_toggle(False)
        self._seed_source(10)
        transfer = self._transfer(4)

        with patch(
            "apex.habitat.doctype.material_transfer.material_transfer.frappe.sendmail"
        ) as sendmail:
            mark_received(transfer.name, "2026-05-03")

        sendmail.assert_not_called()

    def test_no_memo_is_sent_when_both_stores_share_a_cost_centre(self):
        # The destination's cost centre is borrowed from the fixture, so it is handed back.
        self.addCleanup(
            frappe.db.set_value, "Building", DESTINATION,
            "default_cost_center", self.destination_cost_center,
        )
        frappe.db.set_value("Building", DESTINATION, "default_cost_center", self.source_cost_center)
        self._set_finance_toggle(True)
        self._seed_source(10)
        transfer = self._transfer(4)

        with patch(
            "apex.habitat.doctype.material_transfer.material_transfer.frappe.sendmail"
        ) as sendmail:
            mark_received(transfer.name, "2026-05-03")

        sendmail.assert_not_called()

    def test_the_stock_balance_report_reflects_the_completed_transfer(self):
        self._set_finance_toggle(False)
        self._seed_source(10)
        transfer = self._transfer(4)
        mark_received(transfer.name, "2026-05-03")

        _columns, data, *_rest = stock_balance_report({"item_type": "Custody Article"})
        by_building = {r["building"]: r for r in data if r["item"] == self.article and not r["employee"]}

        self.assertEqual(by_building[SOURCE]["balance_qty"], 6.0)
        self.assertEqual(by_building[DESTINATION]["balance_qty"], 4.0)
