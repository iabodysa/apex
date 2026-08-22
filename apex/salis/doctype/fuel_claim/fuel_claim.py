# Copyright (c) 2026, afmcoltd
"""Fuel Claim controller.

Submittable Movement fuel claim and reconciliation against a Fuel Quota.
Movement is a service provider: Operations submits the
claim, Movement reconciles it against the internal Fuel Consumption Ledger.

The controller derives consumed litres from the ledger (sum of litres for the
claim's vehicle + period) and computes the claimed-vs-consumed variance.

Status transitions and the approval authority are owned by the native **Fuel
Claim Workflow** (see ``salis/workflow/fuel_claim_workflow/``), not by this
controller. The workflow enforces the role per transition and the
Segregation-of-Duties gate on the approval (``allow_self_approval=0`` +
``requested_by != session.user``). The document is submitted (docstatus 0 -> 1)
by the ``Approve`` transition, whose ``allowed`` role (Fleet Manager) carries the
governing approval authority; ``Closed`` is the post-submit terminal, reached
from ``Approved`` as a docstatus-1 update (it finalizes, not voids, the claim —
there is no cancel side-effect). The state field is ``allow_on_submit`` so a
post-submit transition can move the status.

This controller keeps only what the workflow cannot express: the required-field
validation, the ledger-derived consumption/variance computation, the financial
reference defaults, the initial-status guard (a claim must be created at Draft),
and the server-side requester stamp the SoD gate relies on.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from apex.salis.utils import set_financial_defaults

_RECONCILED_STATUSES = ("Reconciled", "Approved", "Closed")

_APPROVED_STATUSES = ("Approved", "Closed")

VALID_STATUSES = (
    "Draft",
    "Submitted to Movement",
    "Reconciled",
    "Approved",
    "Disputed",
    "Closed",
)


class FuelClaim(Document):
    def validate(self):
        """Validates the claimed litres and recomputes consumption against the fuel ledger.

        The requester re-stamp here outlives the field's ``__user`` default: that default
        reaches a document only through ``_set_defaults``, which is ``is_new()``-guarded
        and fills a field only when it is None (``frappe/model/document.py:836``), so it
        covers neither a later save nor a request body carrying ``requested_by = ""``. A
        blank requester silently satisfies every ``requested_by != session.user`` gate.
        """
        if not self.requested_by:
            self.requested_by = frappe.session.user
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        if (self.claimed_litres or 0) <= 0:
            frappe.throw(_("Claimed Litres must be greater than zero."))
        set_financial_defaults(self)
        self._compute_consumption()
        self._compute_unit_price()
        self._stamp_reconciliation()
        self._guard_initial_status()

    def _compute_unit_price(self):
        """Derive what the fuel cost per litre from the two numbers the claim already carries.

        Finance checks a fuel claim against the pump price of the month, and a total
        beside a quantity does not state that price. The field is read-only and
        recomputed on every save so it can never disagree with its own arithmetic, and it
        falls back to zero when the litres are missing rather than carrying a stale rate.
        """
        litres = flt(self.claimed_litres)
        self.unit_price_per_litre = (
            flt(flt(self.claimed_amount) / litres, self.precision("unit_price_per_litre"))
            if litres
            else 0
        )

    def _stamp_reconciliation(self):
        """Record when the claim was reconciled and who approved it, and clear both when it falls back.

        The voucher carries two signature lines that nothing on the record filled: the
        movement team who reconciled it and the finance officer who approved it. Both
        stamps go on as those states are reached and come off the moment the claim drops
        back to the movement team or is disputed, so a voucher never prints an approval
        the record no longer holds.
        """
        if self.status in _RECONCILED_STATUSES:
            if not self.reconciled_on:
                self.reconciled_on = nowdate()
        else:
            self.reconciled_on = None

        if self.status in _APPROVED_STATUSES:
            if not self.approved_by:
                self.approved_by = frappe.session.user
        else:
            self.approved_by = None


    def _compute_consumption(self):
        """Derive consumed litres from the Fuel Consumption Ledger and the
		claimed-vs-consumed variance. Consumed litres is the sum of ledger
		litres for this claim's vehicle and period."""
        consumed = 0.0
        if self.vehicle and self.period_month:
            rows = frappe.get_all(
                "Fuel Consumption Ledger",
                filters={"vehicle": self.vehicle, "period_month": self.period_month},
                fields=["litres"],
            )
            consumed = sum((row.litres or 0) for row in rows)

        self.consumed_litres = consumed
        self.variance_litres = (self.claimed_litres or 0) - consumed

    def _guard_initial_status(self):
        """A new claim must be created at the initial state (Draft). Later states
		are reached only through the Fuel Claim Workflow, which the desk drives —
		this closes the insert-bypass the workflow itself cannot cover (a brand-new
		document inserted directly at a later/terminal status)."""
        if self.is_new() and self.status and self.status != "Draft":
            frappe.throw(
                _("A Fuel Claim must be created with status Draft; {0} is reached through the workflow.").format(
                    _(self.status)
                )
            )
