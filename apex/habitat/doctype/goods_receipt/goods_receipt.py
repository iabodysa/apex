# Copyright (c) 2026, afmcoltd


from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    has_stock_entries,
    post_stock_entry,
    reverse_and_mark_cancelled,
    validate_reversal_allowed,
)
from apex.habitat.utils.item_master import resolve_item

VOUCHER_TYPE = "Goods Receipt"


class GoodsReceipt(Document):
    def validate(self):
        if self.intake_building and not frappe.db.get_value(
            "Building", self.intake_building, "is_procurement_store"
        ):
            frappe.throw(
                _("Building {0} is not flagged as a Procurement Intake Store.").format(
                    self.intake_building
                )
            )
        for row in self.items:
            if (row.qty or 0) <= 0:
                frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
            if row.item_type and row.item:
                item_name, uom, _cost = resolve_item(row.item_type, row.item)
                row.item_name = item_name
                row.uom = uom

    def on_submit(self):
        self._post_intake()
        self.db_set("status", "Received")

    def _post_intake(self):
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
        validate_reversal_allowed(VOUCHER_TYPE, self.name)

    def on_cancel(self):
        reverse_and_mark_cancelled(self, VOUCHER_TYPE)
