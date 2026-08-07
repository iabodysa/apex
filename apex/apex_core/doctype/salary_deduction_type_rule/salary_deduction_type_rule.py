# Copyright (c) 2026, afmcoltd
"""Salary Deduction Type Rule (child table).

One row per operational deduction type (Damage / Rent / Fuel / Custody) on the
Salary Deduction Policy. Carries the cap, the max %% of salary, the consent /
approval gate, the schedule, and the triggering event for that type.

This child has no standalone lifecycle. Cross-field validation (e.g. a cap that
exceeds the lawful ceiling, or an enabled rule whose Salary Component is missing
or not of type Deduction) is enforced from the parent ``Salary Deduction Policy``.
"""

from __future__ import annotations

from frappe.model.document import Document


class SalaryDeductionTypeRule(Document):
    pass
