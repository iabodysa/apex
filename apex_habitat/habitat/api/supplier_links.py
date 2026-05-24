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
    # Accommodation Lease / Subcontractor docs use "supplier" (the default);
    # only the ledger/assignment use billed_to_supplier.
    data["non_standard_fieldnames"].update({
        "Accommodation Assignment": "billed_to_supplier",
        "Accommodation Ledger": "billed_to_supplier",
    })
    data["transactions"].extend([
        {"label": "Housing (Supplier-billed)",
         "items": ["Accommodation Assignment", "Accommodation Lease"]},
        {"label": "Subcontracting",
         "items": ["Subcontractor Service Contract", "Subcontractor Service Order"]},
        {"label": "Cost Recovery",
         "items": ["Accommodation Ledger"]},
    ])
    return data
