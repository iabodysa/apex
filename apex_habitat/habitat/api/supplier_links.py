# Copyright (c) 2026, AFMCO and contributors
"""Supplier form-dashboard links for Apex Habitat.

Wired via override_doctype_dashboards in hooks.py. Supplier is an ERPNext
doctype, so this is the only supported mechanism. Frappe passes the native
Supplier dashboard (POs, invoices, payments) as `data`; we MERGE our housing,
subcontracting, and cost-recovery links into it without dropping the native ones.
"""

from __future__ import annotations


def get_data(data=None):
    data = data or {}
    data.setdefault("transactions", [])
    data.setdefault("non_standard_fieldnames", {})
    data["fieldname"] = data.get("fieldname") or "supplier"
    # [#job590]
    data["non_standard_fieldnames"].update({
        "Housing Assignment": "billed_to_supplier",
        "Accommodation Ledger": "billed_to_supplier",
        "Lease": "landlord",
    })
    data["transactions"].extend([
        {"label": "Housing (Supplier-billed)",
         "items": ["Housing Assignment", "Lease"]},
        {"label": "Subcontracting",
         "items": ["Subcontractor Service Contract", "Subcontractor Service Order"]},
        {"label": "Cost Recovery",
         "items": ["Accommodation Ledger"]},
        # [#6f1937]
        {"label": "Fleet (Salis)",
         "items": ["Rental Office"]},
    ])
    return data
