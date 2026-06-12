"""Rental Settlement controller.

Monthly reconciliation of a Rental Office's claim against accrued rental days.
``validate`` recomputes ``accrued_total`` from the vehicle lines (and the line
amounts themselves), cross-checks it against the LINKED Rental Accrual Ledger
total for the same office+period (``ledger_accrued_total`` /
``ledger_variance``), and the ``variance`` against the claimed total. On submit,
``create_payment_request`` may raise a finance-exclusive Salis Payment Request
(expense_type "Rental") referencing this settlement.

Settlement <-> Accrual reconciliation (the second half of the documented
rental-accrual loop): when this settlement reaches a settled state (it is
submitted/Approved, or later marked Paid), the unsettled Rental Accrual Ledger
rows for the same ``rental_office`` + ``period_month`` are stamped
``rental_settlement = <this> / settled = 1`` (``rental_engine.stamp_settlement``;
the ledger grants no human write role so the ``frappe.db.set_value`` bypass is
the correct write path). Cancelling the settlement releases those rows again
(``rental_engine.release_settlement``). The stamp is idempotent — a row already
settled is never re-stamped, and a row owned by another settlement is never
silently re-pointed.

Status transitions are owned by the native **Rental Settlement Workflow** (see
``salis/workflow/rental_settlement_workflow/``), not by this controller. In
particular the "Mark Paid" transition is restricted to the **Finance Manager**
role and carries the Segregation-of-Duties condition ``requested_by !=
session.user`` so the finance approver can never be the (server-stamped)
requester. This controller keeps only the *data* guards (totals, variance, the
known-status check), the server-side requester stamp that the SoD gate relies
on, and the accrual-ledger stamping described above.

This controller posts NO General Ledger / accounting entry. The Salis Payment
Request it raises is a payment request record; Finance posts the actual
payment externally.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

VALID_STATUSES = (
    "Draft",
    "Reconciled",
    "Approved",
    "Paid",
    "Disputed",
    "Cancelled",
)

# The settled states: once the settlement is Approved (the Workflow submit point)
# or Paid, its rental_office+period accrual rows are considered settled and are
# stamped onto it. Both are docstatus=1 in the Rental Settlement Workflow.
SETTLED_STATUSES = ("Approved", "Paid")


class RentalSettlement(Document):
    def before_insert(self):
        # Stamp the requester server-side (read-only field) so the
        # segregation-of-duties / maker-checker gate cannot be spoofed.
        if not self.requested_by:
            self.requested_by = frappe.session.user

    def validate(self):
        # The Select still carries the known states for filtering/colour, but the
        # Rental Settlement Workflow owns *transitions* — this only rejects an
        # unknown value.
        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))

        if not self.requested_by:
            self.requested_by = frappe.session.user
        if not self.company:
            from apex_habitat.apex_core.doctype.salis_settings.salis_settings import (
                get_default_company,
            )

            self.company = get_default_company()

        accrued = 0.0
        for row in self.vehicles:
            # Derive the line amount from days * daily_rate when not supplied.
            computed = flt(row.days) * flt(row.daily_rate)
            if not row.amount:
                row.amount = computed
            # Positivity guard: a negative day count, rate or amount must never
            # flow into the accrued total or the downstream Payment Request.
            if flt(row.days) < 0 or flt(row.daily_rate) < 0 or flt(row.amount) < 0:
                frappe.throw(
                    _("Row {0}: Days, Daily Rate and Amount cannot be negative.").format(row.idx)
                )
            accrued += flt(row.amount)

        # Cross-check / derive against the LINKED Rental Accrual Ledger rows for
        # this office+period — the machine-written source of truth for what was
        # actually accrued. When the office has no hand-entered vehicle lines, the
        # ledger figure IS the accrued total (the controller no longer depends on
        # someone re-keying the days). When lines ARE present, the ledger figure
        # is still stored alongside so the variance against reality is visible and
        # auditable rather than the settlement only checking its own arithmetic.
        from apex_habitat.salis.rental_engine import linked_accrued_total

        ledger_total = linked_accrued_total(self.rental_office, self.period_month)
        self.ledger_accrued_total = flt(ledger_total)

        if accrued:
            self.accrued_total = flt(accrued)
        else:
            self.accrued_total = flt(ledger_total)

        self.ledger_variance = flt(self.accrued_total) - flt(ledger_total)
        self.variance = flt(self.claimed_total) - flt(self.accrued_total)

        # Totals sanity guard: neither the claimed amount nor the derived accrued
        # total may be negative, so no negative value can flow into
        # create_payment_request() and on to the Finance gate. A zero accrued
        # total is a legitimate not-yet-accrued state (the settlement can still sit
        # in the workflow); the actual zero-amount payable is blocked downstream by
        # the Salis Payment Request's own "Amount must be greater than zero" guard.
        if flt(self.claimed_total) < 0 or flt(self.accrued_total) < 0:
            frappe.throw(
                _("Claimed Total and Accrued Total cannot be negative.")
            )

    # --- Settlement <-> Accrual Ledger stamping --------------------------------
    # Status transitions (incl. the submit at "Approved") are driven by the
    # Rental Settlement Workflow, which saves the document. on_submit covers a
    # direct submit; on_update_after_submit covers the post-submit workflow
    # transitions (Approve -> Approved, Mark Paid -> Paid) that the controller
    # would otherwise never see. Both funnel into one idempotent stamp.

    def on_submit(self):
        self._sync_accrual_stamp()

    def on_update_after_submit(self):
        self._sync_accrual_stamp()

    def on_cancel(self):
        # Release the rows so a cancelled settlement no longer counts as settled
        # in the Rental Cost by Office report and a re-issued settlement can claim
        # the same accrual days.
        from apex_habitat.salis.rental_engine import release_settlement

        release_settlement(self.name)

    def _sync_accrual_stamp(self):
        """Stamp this settlement's accrual rows once it is in a settled state.

        Idempotent: ``stamp_settlement`` only touches rows that are still
        ``settled = 0`` and unlinked (or already linked to THIS settlement), so
        repeated post-submit saves (Approve, then Mark Paid) never double-stamp,
        and a row already owned by another settlement is never re-pointed. A
        not-yet-settled docstatus=1 state (none today, but future-proof) stamps
        nothing.
        """
        if self.status not in SETTLED_STATUSES:
            return
        from apex_habitat.salis.rental_engine import stamp_settlement

        stamp_settlement(self.name, self.rental_office, self.period_month)

    @frappe.whitelist(methods=["POST"])
    def create_payment_request(self):
        """Raise a finance-exclusive Salis Payment Request for this settlement.

        Posts NO GL: the Salis Payment Request is a payment request record
        that routes through the Finance approval gate. Idempotent — returns the
        existing linked request if one is already attached.
        """
        if self.docstatus != 1:
            frappe.throw(_("Submit the settlement before raising a payment request."))

        if self.status != "Approved":
            frappe.throw(
                _(
                    "A payment request can only be raised on an Approved settlement "
                    "(current status: {0})."
                ).format(_(self.status))
            )

        if self.payment_request and frappe.db.exists("Salis Payment Request", self.payment_request):
            return self.payment_request

        pr = frappe.get_doc(
            {
                "doctype": "Salis Payment Request",
                "expense_type": "Rental",
                "amount": flt(self.claimed_total) or flt(self.accrued_total),
                "status": "Draft",
                "rental_office": self.rental_office,
                "reference_doctype": "Rental Settlement",
                "reference_name": self.name,
                "remarks": _("Rental settlement {0} for period {1}.").format(
                    self.name, self.period_month
                ),
            }
        )
        pr.insert()

        self.db_set("payment_request", pr.name)
        self.add_comment(
            "Info",
            _("Payment Request {0} raised for {1} SAR.").format(pr.name, pr.amount),
        )
        return pr.name
