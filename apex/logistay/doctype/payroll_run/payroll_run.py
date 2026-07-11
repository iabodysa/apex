# Copyright (c) 2026, AFMCO and contributors
"""Payroll Run controller - 1:1 with a POSTED Reconciliation Run.

Custom code is thin: it names the run (client::branch::period::v{n}), recomputes
the WPS-readiness flags from the linked Salary Slips, and fails the RELEASE
transition closed unless every precondition holds:

* Separation of Duties - preparer != releaser;
* no open consent gaps - every deduction on every slip carries a verified consent;
* WPS-COMPLETE - every included worker has a valid IBAN;
* DoA - the P-193 ``enforce_gate(wps_release)`` allows the amount.

Gross / deduction / net are computed by stock HRMS on the Salary Slips; this
controller only rolls them up and stamps provenance + gate flags.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.logistay.payroll_gate import (
    employee_iban,
    enforce_declaration_gate,
    enforce_release_gate,
    requires_declaration,
    valid_sa_iban,
)


class PayrollRun(Document):
    def autoname(self) -> None:
        # client::branch::period::v{n}; n = existing runs for the same key + 1 (A9 correction wiring).
        n = (
            frappe.db.count(
                "Payroll Run",
                {
                    "pay_client": self.pay_client,
                    "pay_period": self.pay_period,
                    "pay_branch_site": self.pay_branch_site,
                },
            )
            + 1
        )
        parts = [p for p in [self.pay_client, self.pay_branch_site, self.pay_period] if p]
        self.name = "::".join(parts) + f"::v{n}"

    def validate(self) -> None:
        self._enforce_declaration_gate()
        self._recompute_wps_readiness()
        self._enforce_release_preconditions()

    def _enforce_declaration_gate(self) -> None:
        # Slips are held until the period's Deduction Declaration is RECEIVED; this
        # only matters once the run advances to slip-build. Earlier states pass.
        if not requires_declaration(self.pay_status):
            return
        enforce_declaration_gate(self.pay_status, self._declaration_received())

    def _declaration_received(self) -> bool:
        base = {
            "pay_client": self.pay_client,
            "pay_period": self.pay_period,
            "pay_status": "received",
        }
        # A branch-scoped run is covered by a matching branch declaration OR by a
        # client-wide (branch-blank) declaration for the same period.
        if self.pay_branch_site and frappe.db.exists(
            "Deduction Declaration", {**base, "pay_branch_site": self.pay_branch_site}
        ):
            return True
        return bool(
            frappe.db.exists(
                "Deduction Declaration", {**base, "pay_branch_site": ["in", [None, ""]]}
            )
        )

    def _recompute_wps_readiness(self) -> None:
        slips = frappe.get_all(
            "Salary Slip",
            filters={"pay_payroll_run": self.name},
            fields=["name", "employee", "pay_consent_complete"],
        )
        self.pay_worker_count = len(slips)
        self.pay_open_consent_gaps = sum(1 for s in slips if not s.get("pay_consent_complete"))
        # WPS-COMPLETE fails closed: 1 only when there is at least one slip and EVERY
        # included worker resolves to a valid IBAN. Missing/invalid IBAN -> 0 -> release blocked.
        self.pay_iban_complete = (
            1 if slips and all(valid_sa_iban(employee_iban(s.employee)) for s in slips) else 0
        )

    def _enforce_release_preconditions(self) -> None:
        if self.pay_status != "Released":
            return
        # Separation of Duties: the preparer cannot also release the WPS file.
        if self.pay_prepared_by and self.pay_approved_by and self.pay_prepared_by == self.pay_approved_by:
            frappe.throw(_("Separation of duties: the WPS preparer cannot also release it."))
        # Every deduction must carry a verified consent before money leaves.
        if flt(self.pay_open_consent_gaps) > 0:
            frappe.throw(
                _("Cannot release: {0} slip(s) still lack a verified deduction consent.").format(
                    int(self.pay_open_consent_gaps)
                )
            )
        # WPS-COMPLETE precondition (D11): fail closed on any missing/invalid IBAN.
        if not self.pay_iban_complete:
            frappe.throw(_("Cannot release: one or more workers have a missing or invalid IBAN."))
        # DoA release gate resolved by the shared P-193 governance service.
        enforce_release_gate(self)
