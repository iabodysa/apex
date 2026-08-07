# Copyright (c) 2026, afmcoltd
"""Validation for the Saudi National Address custom fields on the native Address."""

import re

import frappe
from frappe import _

SHORT_ADDRESS_PATTERN = re.compile(r"^[A-Za-z]{4}\d{4}$")


def validate(doc, method=None):
    """Enforces the short address, building number and secondary number formats on an Address."""
    short = (doc.get("short_address") or "").strip()
    if short:
        doc.short_address = short.upper()
        if not SHORT_ADDRESS_PATTERN.match(doc.short_address):
            frappe.throw(
                _("Short Address must be 4 letters followed by 4 digits (e.g. RCTB4359)."),
                title=_("Invalid Short Address"),
            )

    for fieldname, label in (("building_number", _("Building Number")), ("secondary_number", _("Secondary Number"))):
        value = (doc.get(fieldname) or "").strip()
        if value and not re.fullmatch(r"\d{4}", value):
            frappe.throw(_("{0} must be a 4-digit number.").format(label))
        doc.set(fieldname, value)
