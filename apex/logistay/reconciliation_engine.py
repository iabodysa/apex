# Copyright (c) 2026, AFMCO and contributors
"""Reconciliation engine guards — the ONE run, TWO outputs invariants (P-190).

STRUCTURE-only home for the reconciliation guards that the ``Reconciliation
Run`` controller invokes from ``validate`` (class-method lifecycle, NOT a
hook). Kept as module functions so the same rule is reused and unit-tested
once:

* ``guard_basis_consistent`` — D1 BASIS-CONSISTENT: the Billable Line and the
  Payable Line derived from the SAME ``Rate Resolution`` must snapshot the
  IDENTICAL ``rec_day_rate_basis_applied``. Any mismatch HALTS the run
  (fail-closed) with ``billing_vs_payable_mismatch``. It compares the BASIS
  itself, never day-counts.
* ``should_apply_thresholds`` — A2/C4 FED-PRECONDITION: a client with no
  per-worker performance feed SKIPS threshold application as a structural
  NO-OP (returns ``False`` → the caller raises nothing and emits zero
  candidates). It is NOT a gate and never zero-fills a candidate.
* ``guard_no_open_gated_threshold`` — an inferred / gated penalty rule forces
  the run to PENDING-REVIEW; POSTing with an open gated item is blocked so the
  engine never invents penalty maths (owner confirms, never invented).

No real value (amount / threshold / SLA number / client name) lives here —
only the enum domain and the guard control-flow.
"""

from __future__ import annotations

import frappe
from frappe import _

# Day-rate basis enum domain — MUST match P-189 ``rc_day_rate_basis`` /
# ``rc_day_rate_basis_applied``. Kept here so the guard and the JSON snapshot
# fields share one source of truth for the basis comparison.
DAY_RATE_BASIS = (
    "actual_cycle_days",
    "fixed_365_12",
    "div_31",
    "explicit_rate_per_day",
)


def guard_basis_consistent(run_name: str) -> None:
    """D1: HALT if a Billable and a Payable line off the SAME Rate Resolution
    snapshot different day-rate bases. Fail-closed — throws, never warns."""
    billable = frappe.get_all(
        "Billable Line",
        filters={"rec_run": run_name},
        fields=["rec_resolution_ref", "rec_day_rate_basis_applied"],
    )
    payable = frappe.get_all(
        "Payable Line",
        filters={"rec_run": run_name},
        fields=["rec_resolution_ref", "rec_day_rate_basis_applied"],
    )
    basis_by_resolution: dict[str, set[str]] = {}
    for row in (*billable, *payable):
        ref = row.get("rec_resolution_ref")
        basis = row.get("rec_day_rate_basis_applied")
        # An unset basis on a priced line is itself an open flag, caught by
        # OPEN-FLAGS-BEFORE-POST; the basis guard compares only KNOWN bases and
        # never silently treats a blank as agreement.
        if not ref or not basis:
            continue
        basis_by_resolution.setdefault(ref, set()).add(basis)
    for ref, bases in basis_by_resolution.items():
        if len(bases) > 1:
            frappe.throw(
                _(
                    "billing_vs_payable_mismatch: Rate Resolution {0} priced the "
                    "Billable and Payable sides on different day-rate bases ({1}). "
                    "The reconciliation is halted until they agree."
                ).format(ref, ", ".join(sorted(bases))),
                title=_("Basis Consistency"),
            )


def should_apply_thresholds(client: str | None) -> bool:
    """A2/C4 FED-PRECONDITION. ``True`` only when the client carries a
    per-worker feed. A ``False`` return means threshold application is a
    structural NO-OP (skip) — NOT a gate and NOT a zero-filled candidate."""
    if not client:
        return False
    return bool(
        frappe.db.get_value(
            "Client Reconciliation Config",
            {"rec_client": client},
            "has_per_worker_feed",
        )
    )


def guard_no_open_gated_threshold(threshold_rows) -> bool:
    """Return ``True`` if any applied threshold row is an INFERRED / gated rule
    (``rec_gated_open_item``). Such a run is forced to PENDING-REVIEW and must
    not POST — the engine never invents penalty maths."""
    return any(getattr(row, "rec_gated_open_item", 0) for row in (threshold_rows or []))
