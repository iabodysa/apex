# Copyright (c) 2026, AFMCO and contributors
"""Validation for the Saudi National Address custom fields on the native Address."""

import re

import frappe
from frappe import _

# SPL Short Address: 4 letters + 4 digits, e.g. RCTB4359.
SHORT_ADDRESS_PATTERN = re.compile(r"^[A-Za-z]{4}\d{4}$")


def validate(doc, method=None):
	short = (doc.get("short_address") or "").strip()
	if short:
		# Normalize to upper-case so RCTB4359 == rctb4359.
		doc.short_address = short.upper()
		if not SHORT_ADDRESS_PATTERN.match(doc.short_address):
			frappe.throw(
				_("Short Address must be 4 letters followed by 4 digits (e.g. RCTB4359)."),
				title=_("Invalid Short Address"),
			)

	# Building / secondary numbers are 4-digit numeric codes.
	for fieldname, label in (("building_number", _("Building Number")), ("secondary_number", _("Secondary Number"))):
		value = (doc.get(fieldname) or "").strip()
		if value and not re.fullmatch(r"\d{4}", value):
			frappe.throw(_("{0} must be a 4-digit number.").format(label))
		doc.set(fieldname, value)
