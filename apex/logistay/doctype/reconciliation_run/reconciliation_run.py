# Copyright (c) 2026, AFMCO and contributors
"""Reconciliation Run controller — ONE run, TWO outputs (P-190).

Aggregates a closed Timesheet Period into a client-side Billable Line set and a
worker-side Payable Line set (plus Deduction Candidates). Only the structural
guards live here; the aggregation / threshold maths live in
``logistay.reconciliation_engine`` and the runtime resolver.

Guards enforced on every save (class-method lifecycle, no hook):

* BASIS-CONSISTENT (D1) — halt on a Billable != Payable day-rate-basis
  mismatch for the same Rate Resolution.
* FED-PRECONDITION snapshot (A2/C4) — record whether threshold application
  runs for this client, or is skipped as a structural no-op.
* GATED-THRESHOLD to PENDING-REVIEW — an inferred penalty rule may not POST.
* OPEN-FLAGS-BEFORE-POST — ``rec_open_flags`` must be 0 to reach posted.
* NEVER-MUTATE-POSTED — a posted run is immutable except a posted to reversed
  move (correction = reverse + re-run).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.logistay.reconciliation_engine import (
    guard_basis_consistent,
    guard_no_open_gated_threshold,
    should_apply_thresholds,
)

_POSTED = "posted"
_REVERSED = "reversed"
_PRE_POST = ("clean", "awaiting_approval", "posted")


class ReconciliationRun(Document):
    def validate(self) -> None:
        self._snapshot_fed_precondition()
        self._guard_gated_threshold()
        self._guard_open_flags_before_post()
        guard_basis_consistent(self.name)
        self._guard_never_mutate_posted()

    def _snapshot_fed_precondition(self) -> None:
        # A2/C4: record whether thresholds apply for this client. A False here
        # means threshold application is SKIPPED as a structural no-op — the run
        # legitimately emits zero Deduction Candidates (never zero-filled).
        self.rec_fed_precondition_met = 1 if should_apply_thresholds(self.rec_client) else 0

    def _guard_gated_threshold(self) -> None:
        # An inferred / gated penalty rule (rec_gated_open_item) forces
        # PENDING-REVIEW: the run may not advance to clean / awaiting / posted
        # with an open gated item. The engine never invents penalty maths.
        if guard_no_open_gated_threshold(self.get("rec_threshold_log")) and self.rec_status in _PRE_POST:
            frappe.throw(
                _(
                    "gated_threshold_open: an inferred penalty rule is unconfirmed; "
                    "this run must stay in pending_review until the owner confirms it."
                ),
                title=_("Gated Threshold"),
            )

    def _guard_open_flags_before_post(self) -> None:
        if self.rec_status == _POSTED and (self.rec_open_flags or 0) != 0:
            frappe.throw(
                _(
                    "open_flags_before_post: {0} open flag(s) remain; resolve them before POST."
                ).format(self.rec_open_flags),
                title=_("Open Flags"),
            )

    def _guard_never_mutate_posted(self) -> None:
        if self.is_new():
            return
        before = frappe.db.get_value("Reconciliation Run", self.name, "rec_status")
        # A posted run is immutable; the ONLY legal move off posted is to
        # reversed (the reverse + re-run correction path).
        if before == _POSTED and self.rec_status != _REVERSED:
            frappe.throw(
                _("never_mutate_posted: a posted run is immutable; correct it with a reversed re-run."),
                title=_("Immutable Run"),
            )
