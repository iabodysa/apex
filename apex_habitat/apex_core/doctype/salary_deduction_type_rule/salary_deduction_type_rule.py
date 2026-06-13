"""Salary Deduction Type Rule (child table).

One row per operational deduction type (Damage / Rent / Fuel / Custody) on the
Salary Deduction Policy. Carries the cap, the max %% of salary, the consent /
approval gate, the schedule, and the triggering event for that type.

Skeleton only: this child has no standalone lifecycle. Cross-field validation
(e.g. a cap that exceeds the lawful ceiling, or an enabled rule whose Salary
Component is missing or not of type Deduction) is enforced from the parent
``Salary Deduction Policy`` and is added when the layer is wired in a later
increment. No existing controller is touched here.
"""

from __future__ import annotations

from frappe.model.document import Document


class SalaryDeductionTypeRule(Document):
    pass
