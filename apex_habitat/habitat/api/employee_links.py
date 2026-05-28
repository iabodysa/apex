"""Employee form-dashboard links for Apex Habitat.

Wired via override_doctype_dashboards in hooks.py. Frappe calls this with the
DocType's native dashboard dict as `data`, so we MERGE into it (append our
transaction groups) instead of replacing — preserving ERPNext's native Employee
dashboard. The previous no-arg signature raised a TypeError when the Employee
form loaded.
"""

from __future__ import annotations


def get_data(data=None):
    data = data or {}
    data.setdefault("transactions", [])
    data.setdefault("non_standard_fieldnames", {})
    data["fieldname"] = data.get("fieldname") or "employee"
    data["non_standard_fieldnames"].update({
        "Custody Issue": "issued_to_employee",
        "Custody Return": "returned_by_employee",
        "Scheduled Task Instance": "assigned_to",
        # Salis Driver Attendance / Vehicle Handover reference the worker via
        # the Salis Driver record, so they surface on the Driver form (one hop),
        # not here. The Movement docs below link Employee directly via "employee".
    })
    data["transactions"].extend([
        {"label": "Accommodation",
         "items": ["Accommodation Assignment", "Accommodation Checkout"]},
        {"label": "Custody",
         "items": ["Custody Issue", "Custody Return", "Custody Damage Assessment"]},
        {"label": "Tasks",
         "items": ["Scheduled Task Instance"]},
        # Salis (Movement) — reference links to HRMS records; writes no accounting documents.
        {"label": "Movement (Salis)",
         "items": ["Salis Driver", "Movement Cost Recovery", "Sponsorship Transfer Case"]},
    ])
    return data
