"""Accommodation Building controller.

Top-level spatial entity. Auto-sums annual cost and recomputes occupancy.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class AccommodationBuilding(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Accommodation Building":
            frappe.throw("DocType mismatch")


def before_save(doc, method=None):
    doc.annual_total_cost_sar = (
        (doc.annual_rent_sar or 0)
        + (doc.annual_electricity_sar or 0)
        + (doc.annual_water_sar or 0)
        + (doc.annual_cleaning_staff_sar or 0)
        + (doc.annual_supervision_sar or 0)
        + (doc.annual_other_expenses_sar or 0)
    )

    if doc.total_capacity:
        doc.annual_cost_per_capacity_sar = doc.annual_total_cost_sar / doc.total_capacity
        doc.monthly_cost_per_capacity_sar = doc.annual_cost_per_capacity_sar / 12

    doc.current_occupants = frappe.db.count(
        "Accommodation Assignment",
        {"building": doc.name, "docstatus": 1, "check_out_date": ["is", "not set"]},
    )
    if doc.total_capacity:
        doc.occupancy_percent = (doc.current_occupants / doc.total_capacity) * 100
