"""Address helpers.

Read a record's display address from the native Frappe **Address** DocType (linked
via Dynamic Link) instead of duplicating address text on the parent. Keeps the parent
record free of a stale address copy while giving callers a plain string to show.
"""

from __future__ import annotations

import frappe


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

    address = get_default_address(doctype, name)
    if not address:
        return ""
    row = frappe.db.get_value(
        "Address",
        address,
        ["address_line1", "address_line2", "city", "state", "pincode", "country"],
        as_dict=True,
    )
    if not row:
        return ""
    return ", ".join(
        part
        for part in (
            row.address_line1,
            row.address_line2,
            row.city,
            row.state,
            row.pincode,
            row.country,
        )
        if part
    )
