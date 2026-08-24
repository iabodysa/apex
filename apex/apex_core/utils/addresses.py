# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.contacts.doctype.address.address import get_default_address


_ADDRESS_PARTS = ["address_line1", "address_line2", "city", "state", "pincode", "country"]


def _address_row_text(address: str | None) -> str:
    if not address:
        return ""
    row = frappe.db.get_value("Address", address, _ADDRESS_PARTS, as_dict=True)
    if not row:
        return ""
    return ", ".join(part for part in (row[p] for p in _ADDRESS_PARTS) if part)


def get_address_text(doctype: str, name: str | None) -> str:
    if not name:
        return ""
    return _address_row_text(get_default_address(doctype, name))


def get_address_text_by_name(address: str | None) -> str:
    return _address_row_text(address)
