# Copyright (c) 2026, AFMCO and contributors
"""Deduction Declaration controller - project-level intake that gates slip build.

The only business rule enforced here is the integrity of the declaration itself:
silence is never clear, and an itemized declaration must actually itemise. The
"hold all slip build until received" rule is a Workflow/Payroll-Run precondition,
not enforced on this record.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class DeductionDeclaration(Document):
    def autoname(self) -> None:
        parts = [p for p in [self.pay_client, self.pay_branch_site, self.pay_project, self.pay_period] if p]
        self.name = "::".join(parts)

    def validate(self) -> None:
        # Silence is never clear: a 'clear' declaration must explicitly confirm no deductions.
        if self.pay_declaration_type == "clear" and not self.pay_no_deductions_stated:
            frappe.throw(
                _("A 'clear' declaration must explicitly confirm no deductions; silence is not clear.")
            )
        if self.pay_declaration_type == "itemized" and not (self.pay_itemized_list or "").strip():
            frappe.throw(_("An itemized declaration must list the declared deductions."))
