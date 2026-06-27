"""Salary Deduction Policy (Single).

Governs whether, and how, operational events (damage, rent, fuel, custody) may be
deducted from a worker's salary. Native-first: the deduction itself is an HRMS
``Additional Salary`` posting an HRMS ``Salary Component`` of type Deduction — this
policy only decides if/when/how-much, it does not reimplement payroll.

Default is NO deduction: ``enable_salary_deductions`` is OFF and every type rule
ships disabled. Conservative, KSA-Labor-Law-aligned caps are pre-filled (per-type
max %% well under the 50%% Art. 91 combined-wage ceiling) and a standing legal-review
flag is kept ON.

Skeleton only. The light integrity checks below are self-contained (they read only
this Single and the referenced Salary Component); they do NOT wire into or import any
operational controller — that wiring is a later increment.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

# [#bi6a6t]
KSA_MAX_TOTAL_DEDUCTION_PERCENT = 50.0


class SalaryDeductionPolicy(Document):
    def validate(self):
        self._guard_global_cap()
        self._guard_type_rules()

    def _guard_global_cap(self):
        """The combined ceiling must never exceed the lawful 50%% (Art. 91)."""
        if flt(self.global_max_percent_of_salary) > KSA_MAX_TOTAL_DEDUCTION_PERCENT:
            frappe.throw(
                _(
                    "Global Max % of Salary cannot exceed {0}% (KSA Labor Law Art. 91 ceiling on combined wage deductions)."
                ).format(KSA_MAX_TOTAL_DEDUCTION_PERCENT)
            )

    def _guard_type_rules(self):
        """For each ENABLED type rule, keep its cap lawful and its Salary Component
        valid. Disabled rows are left untouched so a half-configured rule can be saved
        as a draft and finished later (it simply never fires while disabled)."""
        # A deliberate 0% global cap (deductions effectively disabled by ceiling) must
        # be honoured, not swallowed by `or` as if unset; fall back to the legal ceiling
        # only when the field is genuinely empty (None / "").
        raw_cap = self.global_max_percent_of_salary
        global_cap = flt(raw_cap) if raw_cap not in (None, "") else KSA_MAX_TOTAL_DEDUCTION_PERCENT
        for row in self.type_rules or []:
            if not row.enabled:
                continue
            if flt(row.max_percent_of_salary) > global_cap:
                frappe.throw(
                    _(
                        "Deduction type {0}: Max % of Salary ({1}%) cannot exceed the global ceiling ({2}%)."
                    ).format(row.deduction_type, flt(row.max_percent_of_salary), global_cap)
                )
            component = row.salary_component or self.default_salary_component
            if not component:
                frappe.throw(
                    _("Deduction type {0} is enabled but has no Salary Component (and no default is set).").format(
                        row.deduction_type
                    )
                )
            comp_type = frappe.db.get_value("Salary Component", component, "type")
            if comp_type and comp_type != "Deduction":
                frappe.throw(
                    _("Salary Component {0} must be of type Deduction (deduction type {1}).").format(
                        component, row.deduction_type
                    )
                )
