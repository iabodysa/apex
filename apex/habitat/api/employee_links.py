# Copyright (c) 2026, afmcoltd

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
