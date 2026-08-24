# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import hashlib
import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, flt, now_datetime

from apex.apex_core.utils.otp_lockout import clear_lockout
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
    reverse_and_mark_cancelled,
    validate_reversal_allowed,
)
from apex.habitat.utils.item_master import resolve_item

VOUCHER_TYPE = "Custody Handover"


class CustodyHandover(Document):
    def validate(self):
        if self.from_building and self.to_building and self.from_building == self.to_building:
            frappe.throw(_("Source and destination buildings must be different."))
        if self.procurement_supervisor and self.receiving_supervisor and self.procurement_supervisor == self.receiving_supervisor:
            frappe.throw(_("The procurement supervisor and the receiving supervisor must be different people."))
        for row in self.items:
            if (row.qty or 0) <= 0:
                frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
            if row.item_type and row.item:
                item_name, uom, _cost = resolve_item(row.item_type, row.item)
                row.item_name = item_name
                row.uom = uom

    def on_submit(self):
        self._assert_source_availability()
        self._post_ship_leg()
        self.db_set("status", "Pending Receipt")
        code = generate_otp(self)
        frappe.response["handover_otp"] = code

    def before_cancel(self):
        validate_reversal_allowed(VOUCHER_TYPE, self.name)

    def on_cancel(self):
        reverse_and_mark_cancelled(self, VOUCHER_TYPE)

    def _assert_source_availability(self):
        needed = {}
        for row in self.items:
            needed[(row.item_type, row.item)] = needed.get((row.item_type, row.item), 0) + flt(row.qty)
        for (item_type, item), qty in needed.items():
            available = get_store_balance(item_type, item, self.from_building, for_update=True)
            if qty > available:
                frappe.throw(
                    _("Cannot hand over {0} unit(s) of {1} from {2}: only {3} available in the store.").format(
                        qty, item, self.from_building, available
                    )
                )

    def _post_ship_leg(self):
        if has_stock_entries(VOUCHER_TYPE, self.name):
            return
        for row in self.items:
            post_stock_entry(
                item_type=row.item_type, item=row.item, qty=-flt(row.qty),
                building=self.from_building, employee=None,
                from_building=self.from_building, to_building=self.to_building,
                voucher_type=VOUCHER_TYPE, voucher_no=self.name, voucher_detail_no=row.name,
                posting_date=self.handover_date,
            )


def hash_otp(code: str, name: str) -> str:
    return hashlib.sha256((code + name).encode()).hexdigest()


def generate_otp(doc) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    validity = frappe.db.get_single_value("Habitat Settings", "handover_otp_validity_minutes") or 10
    doc.db_set({
        "otp_hash": hash_otp(code, doc.name),
        "otp_expires_at": add_to_date(now_datetime(), minutes=int(validity)),
        "otp_attempts": 0,
        "otp_locked_until": None,
    })
    clear_lockout(doc.doctype, doc.name)
    return code
