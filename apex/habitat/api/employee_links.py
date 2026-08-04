# Copyright (c) 2026, AFMCO and contributors
"""Employee form-dashboard links for Apex Habitat.

Wired via override_doctype_dashboards in hooks.py. Frappe calls this with the
DocType's native dashboard dict as `data`, so we MERGE into it (append our
transaction groups) instead of replacing — preserving ERPNext's native Employee
dashboard. The previous no-arg signature raised a TypeError when the Employee
form loaded.
"""

from __future__ import annotations

import frappe


def get_data(data=None):
    data = data or {}
    data.setdefault("transactions", [])
    data.setdefault("non_standard_fieldnames", {})
    data["fieldname"] = data.get("fieldname") or "employee"
    data["non_standard_fieldnames"].update({
        "Custody Issue": "issued_to_employee",
        "Custody Return": "returned_by_employee",
        "Scheduled Task Instance": "assigned_to",
    })
    data["transactions"].extend([
        {"label": frappe._("Accommodation"),
         "items": ["Housing Assignment", "Housing Checkout"]},
        {"label": frappe._("Custody"),
         "items": ["Custody Issue", "Custody Return", "Custody Damage Assessment"]},
        {"label": frappe._("Tasks"),
         "items": ["Scheduled Task Instance"]},
        {"label": frappe._("Salis"),
         "items": ["Salis Driver", "Movement Cost Recovery"]},
    ])
    return data
