# Copyright (c) 2026, AFMCO and contributors

"""Goods Receipt controller — books externally-purchased goods INTO a
procurement intake store via the Accommodation Stock Ledger. This is the first leg of
the procurement -> handover -> custody chain: stock lands unassigned in the intake
building's store (employee unset) and is later handed over into custody.

Lifecycle: Draft -> (submit) Received -> (handover, later wave) Handed Over; cancel
reverses every ledger row this receipt posted. Modeled on Accommodation Material
Transfer (same post_stock_entry / has_stock_entries / reverse_stock_entries engine).
Lifecycle logic lives as Document methods so Frappe runs it natively with no hook."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

VOUCHER_TYPE = "Goods Receipt"


class GoodsReceipt(Document):
    def validate(self):
        if not self.items:
            frappe.throw(_("At least one item is required on a Goods Receipt."))
        if self.intake_building and not frappe.db.get_value(
            "Building", self.intake_building, "is_procurement_store"
        ):
            frappe.throw(
                _("Building {0} is not flagged as a Procurement Intake Store.").format(
                    self.intake_building
                )
            )
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            _resolve_item,
        )
        for row in self.items:
            if (row.qty or 0) <= 0:
                frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
            if row.item_type and row.item:
                item_name, uom, _cost = _resolve_item(row.item_type, row.item)
                row.item_name = item_name
                row.uom = uom

    def on_submit(self):
        """Book each line INTO the intake building store and mark the receipt Received."""
        self._post_intake()
        self.db_set("status", "Received")

    def _post_intake(self):
        """Stock lands unassigned in the intake building store (employee unset). Idempotent."""
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            post_stock_entry, has_stock_entries,
        )
        if has_stock_entries(VOUCHER_TYPE, self.name):
            return
        for row in self.items:
            post_stock_entry(
                item_type=row.item_type, item=row.item, qty=flt(row.qty),
                building=self.intake_building, employee=None,
                to_building=self.intake_building,
                voucher_type=VOUCHER_TYPE, voucher_no=self.name, voucher_detail_no=row.name,
                posting_date=self.receipt_date,
            )

    def before_cancel(self):
        """Refuse the cancel here, not in on_cancel: this runs before db_update()
        stamps docstatus 2, so a receipt whose goods have already left the store is
        left submitted instead of reading as cancelled for the rest of the request."""
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            assert_reversal_allowed,
        )
        assert_reversal_allowed(VOUCHER_TYPE, self.name)

    def on_cancel(self):
        """Reverse every ledger row this receipt posted."""
        from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
            reverse_and_mark_cancelled,
        )
        reverse_and_mark_cancelled(self, VOUCHER_TYPE)
