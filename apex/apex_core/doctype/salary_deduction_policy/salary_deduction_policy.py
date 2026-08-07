# Copyright (c) 2026, afmcoltd
"""Salary Deduction Policy (Single).

Governs whether, and how, operational events (damage, rent, fuel, custody) may be
deducted from a worker's salary. Native-first: the deduction itself is an HRMS
``Additional Salary`` posting an HRMS ``Salary Component`` of type Deduction — this
policy only decides if/when/how-much, it does not reimplement payroll.

Default is NO deduction: ``enable_salary_deductions`` is OFF and every type rule
ships disabled. Conservative, KSA-Labor-Law-aligned caps are pre-filled (per-type
max %% well under the 50%% Art. 91 combined-wage ceiling) and a standing legal-review
flag is kept ON.

Single source of truth: operational controllers read their per-type config through
``get_type_rule(rule_type)`` (or the ``get_damage_rule`` helper) — a rule is returned
only when BOTH the global master switch and that row's ``enabled`` flag are ON, so the
master switch genuinely gates every type. The Custody Damage Assessment controller
(damage rule) and the Accommodation Assignment controller (rent / housing rule) are
wired to these accessors.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

KSA_MAX_TOTAL_DEDUCTION_PERCENT = 50.0


class SalaryDeductionPolicy(Document):
    def validate(self):
        """Runs the global cap, per-type rule, authorization, and recovery-account guards."""
        self._guard_global_cap()
        self._guard_type_rules()
        self._guard_authorization()
        self._guard_recovery_account_agreement()

    def _guard_recovery_account_agreement(self):
        """A Damage rule's component must credit the account the advance debited.

        Enforced here, at configuration, and never at recovery time: refusing mid-run
        would silently stop a worker's wage recovery, which is worse than refusing a
        save the operator is already looking at.

        """
        for row in self.type_rules or []:
            if not row.enabled or row.deduction_type != "Damage":
                continue
            component = row.salary_component or self.default_salary_component
            if not component:
                continue
            for account_row in frappe.get_all(
                "Salary Component Account",
                filters={"parent": component},
                fields=["company", "account"],
            ):
                advance_account = frappe.db.get_value(
                    "Company", account_row.company, "default_employee_advance_account"
                )
                if advance_account and account_row.account != advance_account:
                    frappe.throw(
                        _(
                            "Salary Component {0} posts to {1} for company {2}, but employee "
                            "advances are paid from {3}. Damage recovery would clear the "
                            "deduction without clearing the advance. Point both at one account."
                        ).format(component, account_row.account, account_row.company, advance_account)
                    )

    def _guard_authorization(self):
        """An enabled Rent / Housing rule needs a recorded authorizer and document
        (management sign-off), mirroring the gate that previously lived on Habitat
        Settings. Activation date defaults to today when left blank."""
        for row in self.type_rules or []:
            if not row.enabled or row.deduction_type != "Rent":
                continue
            if not row.authorized_by:
                frappe.throw(
                    _("Authorized By is required to enable the Rent / Housing deduction rule.")
                )
            if not row.authorization_document:
                frappe.throw(
                    _("Authorization Document is required to enable the Rent / Housing deduction rule.")
                )
            if not row.activation_date:
                row.activation_date = today()

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

    def get_type_rule(self, rule_type):
        """The ENABLED type rule for ``rule_type`` (Damage / Rent / Fuel / Custody), or None.

        Returns the row only when the global master switch (``enable_salary_deductions``)
        AND the row's own ``enabled`` flag are both ON — so the master switch gates every
        type. The first matching enabled row wins. ``None`` means "do not deduct this type".
        """
        if not self.enable_salary_deductions:
            return None
        for row in self.type_rules or []:
            if row.deduction_type == rule_type and row.enabled:
                return row
        return None


def get_policy():
    """The Salary Deduction Policy Single document."""
    return frappe.get_single("Salary Deduction Policy")


def get_damage_rule():
    """The enabled Damage deduction rule (or None) from the Salary Deduction Policy."""
    return get_policy().get_type_rule("Damage")
