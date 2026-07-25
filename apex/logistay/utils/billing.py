# Copyright (c) 2026, AFMCO and contributors
"""Billing math shared by the read API and the cost-allocation report."""

from __future__ import annotations

from frappe.utils import flt


def monthly_equivalent(amount, frequency) -> float:
    """Normalize a recurring charge to a comparable monthly figure."""
    amount = flt(amount)
    if frequency == "Quarterly":
        return amount / 3.0
    if frequency == "Annually":
        return amount / 12.0
    return amount
