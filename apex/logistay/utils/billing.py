# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from frappe.utils import flt


def monthly_equivalent(amount, frequency) -> float:
    amount = flt(amount)
    if frequency == "Quarterly":
        return amount / 3.0
    if frequency == "Annually":
        return amount / 12.0
    return amount
