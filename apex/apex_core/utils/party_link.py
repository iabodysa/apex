# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _

PARTY_EMPLOYEE = "Employee"
PARTY_TEMPORARY_WORKER = "Temporary Worker"
PARTY_TYPE_OPTIONS = f"{PARTY_EMPLOYEE}\n{PARTY_TEMPORARY_WORKER}"


def sync_party_employee(
    doc,
    derive_from: str | None = None,
    require_party: bool = False,
    employee_field: str = "employee",
) -> None:
    if derive_from and not doc.get("party"):
        parent = doc.get(derive_from)
        if parent:
            parent_doctype = doc.meta.get_field(derive_from).options
            row = frappe.db.get_value(parent_doctype, parent, ["party_type", "party"])
            if row and row[0]:
                doc.party_type, doc.party = row[0], row[1]

    if not doc.get("party_type") and doc.get(employee_field):
        doc.party_type = PARTY_EMPLOYEE

    if doc.get("party_type") == PARTY_EMPLOYEE:
        if doc.get("party"):
            setattr(doc, employee_field, doc.party)
        elif doc.get(employee_field):
            doc.party = doc.get(employee_field)
    elif doc.get("party_type") == PARTY_TEMPORARY_WORKER:
        setattr(doc, employee_field, None)

    if require_party and not doc.get("party") and not doc.get(employee_field):
        frappe.throw(_("Resident / worker is required."), frappe.MandatoryError)
