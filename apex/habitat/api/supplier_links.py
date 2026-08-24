# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe


def get_data(data=None):
    data = data or {}
    data.setdefault("transactions", [])
    data.setdefault("non_standard_fieldnames", {})
    data["fieldname"] = data.get("fieldname") or "supplier"
    data["non_standard_fieldnames"].update({
        "Housing Assignment": "billed_to_supplier",
        "Accommodation Ledger": "billed_to_supplier",
        "Lease": "landlord",
    })
    data["transactions"].extend([
        {"label": frappe._("Housing (Supplier-billed)"),
         "items": ["Housing Assignment", "Lease"]},
        {"label": frappe._("Subcontracting"),
         "items": ["Subcontractor Service Contract", "Subcontractor Service Order"]},
        {"label": frappe._("Cost Recovery"),
         "items": ["Accommodation Ledger"]},
        {"label": frappe._("Fleet (Salis)"),
         "items": ["Rental Office"]},
    ])
    return data
