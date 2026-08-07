# Copyright (c) 2026, afmcoltd
"""Address helpers.

Read a record's display address from the native Frappe **Address** DocType (linked
via Dynamic Link) instead of duplicating address text on the parent. Keeps the parent
record free of a stale address copy while giving callers a plain string to show.
"""

from __future__ import annotations

import frappe


_ADDRESS_PARTS = ["address_line1", "address_line2", "city", "state", "pincode", "country"]


def _address_row_text(address: str | None) -> str:
    """Comma-join the non-empty parts of one Address record (perm-safe db read)."""
    if not address:
        return ""
    row = frappe.db.get_value("Address", address, _ADDRESS_PARTS, as_dict=True)
    if not row:
        return ""
    return ", ".join(part for part in (row[p] for p in _ADDRESS_PARTS) if part)


def get_address_text(doctype: str, name: str | None) -> str:
    """Plain single-line display of the default native Address linked to ``doctype`` /
    ``name`` (non-empty parts comma-joined).

    Permission-safe for guest / portal contexts: it reads via ``frappe.db.get_value``
    and never calls ``Address.check_permission()``, so a token-authenticated worker
    (session user = Guest) can render their building address. Returns plain text (no
    HTML), so it renders cleanly both in print templates and in the worker-portal SPA.
    Empty string when nothing is linked.
    """
    if not name:
        return ""
    from frappe.contacts.doctype.address.address import get_default_address

    return _address_row_text(get_default_address(doctype, name))


def get_address_text_by_name(address: str | None) -> str:
    """Plain single-line display of a specific Address record by its docname."""
    return _address_row_text(address)
